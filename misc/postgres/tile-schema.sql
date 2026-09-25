

--
-- computation on grid tiles schema
--

--
-- computations in system
-- every computation for grid tiles should have a
-- natural resolution (the z-level in xyz tiles)

CREATE TABLE computation_master (
    computation_id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    zoom_level INTEGER NOT NULL CHECK (zoom_level BETWEEN 0 AND 30),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT comp_unique_name UNIQUE (name)
);


--
-- 2: store polygon data as binary JSON
--

CREATE TABLE polygon_master (
    polygon_id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    raw_geometry JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT polygon_unique_name UNIQUE (name)
);


CREATE INDEX idx_polygon_master_geometry ON polygon_master USING GIN (raw_geometry);

--
-- 3. when a polygon subscribes a computation, record the subscription,
-- generate new computation_tile or find existing and update in
-- polygon_tile_mapper and computation_tile_mapper
--

CREATE TABLE polygon_computation (
    polygon_comp_id BIGSERIAL PRIMARY KEY,
    polygon_id BIGINT NOT NULL REFERENCES polygon_master(polygon_id) ON DELETE CASCADE,
    computation_id BIGINT NOT NULL REFERENCES computation_master(computation_id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_polygon_comp UNIQUE (polygon_id, computation_id)
);


--
-- 4. master list of geo tiles that we need to track
-- across polygons and computations.
--

CREATE TABLE geo_tiles (
    tile_id BIGINT PRIMARY KEY,
    tile_z INTEGER NOT NULL CHECK (tile_z BETWEEN 0 AND 30),
    tile_x INTEGER NOT NULL,
    tile_y INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_geo_tile UNIQUE (tile_z, tile_x, tile_y)
);



-- 5. resolve a polygon into tiles at a zoom level
-- area_fraction is a measure of tile area enclosed by polygon
-- An outside process will populate this table. We add an entry for
-- every computation_tile
--

CREATE TABLE polygon_tiles (
    polygon_tile_id BIGSERIAL PRIMARY KEY,
    polygon_id BIGINT NOT NULL REFERENCES polygon_master(polygon_id) ON DELETE CASCADE,
    tile_id BIGINT NOT NULL REFERENCES geo_tiles(tile_id) ON DELETE RESTRICT,
    area_fraction NUMERIC(5, 4) NOT NULL CHECK (area_fraction > 0 AND area_fraction <= 1),
    CONSTRAINT unique_polygon_tile UNIQUE (polygon_id, tile_id)
);

CREATE INDEX idx_polygon_tile ON polygon_tiles(tile_id);


--
-- 6. what tiles a computation is supposed to run on
--
--
CREATE TABLE computation_tiles (
    computation_tile_id BIGSERIAL PRIMARY KEY,
    computation_id BIGINT REFERENCES computation_master(computation_id) ON DELETE CASCADE,
    tile_id BIGINT REFERENCES geo_tiles(tile_id) ON DELETE CASCADE,
    CONSTRAINT unique_computation_tile UNIQUE (computation_id, tile_id)
);

CREATE INDEX idx_comp_tile ON computation_tiles(computation_id);


---
--- 7.
---

CREATE TABLE computation_run (
    run_uuid UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    computation_id BIGINT REFERENCES computation_master(computation_id),
    status VARCHAR(50) DEFAULT 'PENDING', -- PENDING, PROCESSING, COMPLETED, FAILED
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_comp_run_comp ON computation_run(computation_id);
CREATE INDEX idx_comp_run_status ON computation_run(status) WHERE status IN ('PENDING', 'PROCESSING');


-- Stores the computation output (metrics, multi-values, or arrays)
-- against a tile on the grid
--


CREATE TABLE computation_result (
    result_id BIGSERIAL PRIMARY KEY,
    run_uuid UUID REFERENCES computation_run(run_uuid) ON DELETE CASCADE,
    tile_id BIGINT REFERENCES computation_tile(tile_id) ON DELETE CASCADE,
    result JSONB NOT NULL,
    computed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_run_tile_result UNIQUE (run_uuid, comp_tile_id)
);

CREATE INDEX idx_comp_result_run ON computation_result(run_uuid);
CREATE INDEX idx_comp_result_data ON computation_result USING GIN (result);


