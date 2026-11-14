-- Runs once on first start of an empty volume.
CREATE EXTENSION IF NOT EXISTS vector;
-- Separate schemas keep the simulator's data apart from GigBid's own tables.
CREATE SCHEMA IF NOT EXISTS gigsim;
CREATE SCHEMA IF NOT EXISTS gigbid;
