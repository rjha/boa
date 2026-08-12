import os
import io
import json
import logging
from enum import Enum
from pathlib import Path
from functools import lru_cache
from dataclasses import dataclass
from logging.handlers import WatchedFileHandler
from typing import Dict, Any, Optional

# ==============================================================================
# 1. TYPE DECLARATIONS & CONTAINERS (IMMUTABLE RECORDS)
# ==============================================================================

class DatabaseType(Enum):
    PRODUCTION = "production"
    DEV = "dev"

class ConfigPathCode(Enum):
    SUCCESS = 0
    BAD_ENV_PATH = 1
    BAD_SYSTEM_PATH = 2
    ERR_UNHANDLED_EXCEPTION = 3
    ERR_JSON_PARSE_FAILED = 4

@dataclass(frozen=True)
class ConfigPathResult:
    status: ConfigPathCode
    file_path: Optional[Path]
    audit_log: str
    error: Optional[str] = None

@dataclass(frozen=True)
class DatabaseConfig:
    db_user: str
    db_password: str
    db_host: str
    db_port: int
    db_name: str

@dataclass(frozen=True)
class LoggerConfig:
    log_file: str
    log_level: int

# ==============================================================================
# 2. INTERNAL PATH LOCATOR
# ==============================================================================

def _get_config_path() -> ConfigPathResult:
    """
    Locates the worker_config.json file using a prioritized multi-tier lookup 
    hierarchy. (1) first check the BOA_CONFIG_PATH environment variable. 
    if that is not available then $HOME/sw/.softmaxx/boa is checked next, followed by 
    /usr/local/etc/softmaxx/boa and /etc/softmaxx/boa folders. 
    Checks the environment variable first, then system fallback locations.
    """
    log_stream = io.StringIO()
    target_filename = "boa_config.json"
    
    try:
        # is environment variable set?
        env_path_str = os.environ.get("BOA_CONFIG_PATH")
        if env_path_str:
            env_path = Path(env_path_str).resolve()
            log_stream.write("BOA_CONFIG_PATH=[{0}]\n".format(env_path))
            
            if env_path.exists() and env_path.is_file():
                log_stream.write("BOA_CONFIG_PATH is set and file exists.\n")
                return ConfigPathResult(
                    ConfigPathCode.SUCCESS, 
                    env_path, 
                    log_stream.getvalue()
                )
            else:
                log_stream.write("BOA_CONFIG_PATH is not set or points to a bad location\n")
                
        log_stream.write("no config found via environment. checking system paths...\n")
        # search system paths for config file
        search_locations = [
            Path.home() / "sw" / ".softmaxx/boa" / target_filename,
            Path("/usr/local/etc/softmaxx/boa") / target_filename,
            Path("/etc/softmaxx/boa") / target_filename
        ]
        
        for path in search_locations:
            try:
                resolved_path = path.resolve()
                log_stream.write("checking location: {0} -> ".format(resolved_path))
                
                if resolved_path.exists() and resolved_path.is_file():
                    log_stream.write("found config file at location\n")
                    return ConfigPathResult(
                        ConfigPathCode.SUCCESS, 
                        resolved_path, 
                        log_stream.getvalue()
                    )
                
            except PermissionError:
                log_stream.write("permission denied!!\n")
        
        # no config file in system paths also!
        log_stream.write("no worker_config.json found in system paths.\n")
        return ConfigPathResult(
            ConfigPathCode.BAD_SYSTEM_PATH,
            None,
            log_stream.getvalue()
        )

    except Exception as exc:
        log_stream.write("unknown error during config file lookup.\n")
        
        return ConfigPathResult(
            ConfigPathCode.ERR_UNHANDLED_EXCEPTION,
            None,
            log_stream.getvalue(),
            repr(exc)
        )
    finally:
        log_stream.close()

# ==============================================================================
# 3. APPLICATIVE CONFIGURATION ENGINE
# ==============================================================================

class AppConfig:
    _container: Dict[str, Any] = {}

    @staticmethod
    def load() -> None:
        """
        get the worker config file, parse and load it into _container 
        """
        config_path_result = _get_config_path()
        audit_log = io.StringIO()
        audit_log.write(config_path_result.audit_log)
        
        if config_path_result.status != ConfigPathCode.SUCCESS:
            error_msg = "code: {0}\n log: {1}\n error:{2}\n".format(
                config_path_result.status.name, 
                audit_log.getvalue(), 
                config_path_result.error
            )
            audit_log.close()
            raise RuntimeError(error_msg)

        try:
            audit_log.write("reading configuration from file: {0}\n".format(config_path_result.file_path))
            with open(config_path_result.file_path, "r") as json_file:
                AppConfig._container = json.load(json_file)

            audit_log.write("application configuration loaded into memory.\n")

        except Exception as json_err:
            error_msg = "JSON Parse Error: {0}\n log:\n{1}".format(repr(json_err), audit_log.getvalue())
            raise RuntimeError(error_msg)
        finally:
            audit_log.close()

    @staticmethod
    def get(key: str) -> Any:
        """
        Fetches raw elements, arrays, or child JSON blocks directly from the 
        configuration container by string key. Raises KeyError if missing.
        """
        if key not in AppConfig._container:
            raise KeyError("fatal: configuration key '{0}' is missing.".format(key))
        return AppConfig._container[key]


    @staticmethod
    def init_logging(log_file: str, log_level: int) -> None:
        """
        Reads logging configuration parameters from AppConfig and init 
        the root logger. Since we are using logrotate to rotate logs,
        we use WatchedFileHandler instead of RotatingFilehandler. 
        
        If your operating system manages log rotations centrally via logrotate,
        a standard RotatingFileHandler will conflict with it. When logrotate 
        moves or renames the active log file (e.g., softmaxx.log to softmaxx.log.1), 
        RotatingFileHandler keeps writing to the renamed file descriptor because 
        it has no awareness of external OS file swaps.

        WatchedFileHandler specifically watches the file on disk. The instant 
        logrotate cuts a new file, the handler detects that the file's underlying 
        inode changed, closes its old reference, and seamlessly closes and 
        re-opens the correct target log path without dropping log rows or 
        requiring a service restart

        """
        if not log_level:
            raise RuntimeError("fatal: log_level parameter missing for init_logging()")

        if not log_file:
            raise RuntimeError("fatal: log_file path parameter missing for init_logging()")

        log_format = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s.%(funcName)s:(%(lineno)d) - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        file_handler = WatchedFileHandler(log_file)
        file_handler.setFormatter(log_format)
        
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(log_format)
        
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        root_logger.handlers.clear()
        
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
        logging.info("init_logging() done, writing logs to target file: {0}".format(log_file))

# ==============================================================================
# 4. MODULE-LEVEL FUNCTIONS
# ==============================================================================

@lru_cache(maxsize=len(DatabaseType))
def get_database_config(db_type: DatabaseType=DatabaseType.DEV) -> DatabaseConfig:
    """
    Extracts a strongly-typed, immutable credential block corresponding 
    to the DatabaseType Enum selector (PRODUCTION or DEV). Cached.
    """
    database_section = AppConfig.get("database") 
    data = database_section[db_type.value]
    
    return DatabaseConfig(
        db_user=str(data["user"]),
        db_password=str(data["password"]),
        db_host=str(data["host"]),
        db_port=int(data["port"]),
        db_name=str(data["database"])
    )


@lru_cache(maxsize=1)
def get_logger_config(name: str) -> LoggerConfig:
    """
    Extracts logging config parameters from AppConfig and wraps them inside
    an immutable frozen LoggerConfig dataclass. Cached.
    """
    log_section = AppConfig.get("logging")
    data = log_section[name]
    
    return LoggerConfig(
        log_file=str(data["log_file"]),
        log_level=int(data["log_level"])
    )
