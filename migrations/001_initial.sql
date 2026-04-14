-- Extreme-conditions plant database — initial schema (SQLite)

PRAGMA foreign_keys = ON;

CREATE TABLE plant_type (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  description TEXT
);

CREATE TABLE growing_medium (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  description TEXT
);

CREATE TABLE environment_condition (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT,
  severity_scale INTEGER,
  is_speculative INTEGER NOT NULL DEFAULT 0 CHECK (is_speculative IN (0, 1))
);

CREATE TABLE survival_factor (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  description TEXT
);

CREATE TABLE environment_condition_survival_factor (
  environment_condition_id INTEGER NOT NULL REFERENCES environment_condition(id) ON DELETE CASCADE,
  survival_factor_id INTEGER NOT NULL REFERENCES survival_factor(id) ON DELETE CASCADE,
  relevance TEXT CHECK (relevance IN ('primary', 'secondary')),
  PRIMARY KEY (environment_condition_id, survival_factor_id)
);

CREATE TABLE plant (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scientific_name TEXT NOT NULL UNIQUE,
  common_names TEXT NOT NULL DEFAULT '[]',
  plant_type_id INTEGER NOT NULL REFERENCES plant_type(id),
  life_cycle TEXT NOT NULL CHECK (life_cycle IN ('annual', 'perennial', 'biennial')),
  native_regions TEXT,
  edible_parts TEXT NOT NULL DEFAULT '[]',
  toxicity_notes TEXT,
  image_url TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE growing_profile (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  plant_id INTEGER NOT NULL REFERENCES plant(id) ON DELETE CASCADE,
  environment_condition_id INTEGER NOT NULL REFERENCES environment_condition(id) ON DELETE CASCADE,
  medium_id INTEGER NOT NULL REFERENCES growing_medium(id) ON DELETE RESTRICT,
  hardiness_zone_min INTEGER,
  hardiness_zone_max INTEGER,
  summary TEXT,
  difficulty TEXT NOT NULL CHECK (difficulty IN ('beginner', 'intermediate', 'advanced')),
  confidence_level TEXT NOT NULL CHECK (confidence_level IN ('peer_reviewed', 'field_practice', 'speculative')),
  last_reviewed_at TEXT,
  climate_context TEXT,
  UNIQUE (plant_id, environment_condition_id, medium_id)
);

CREATE TABLE growing_step (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  growing_profile_id INTEGER NOT NULL REFERENCES growing_profile(id) ON DELETE CASCADE,
  step_order INTEGER NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  duration_days INTEGER,
  equipment TEXT,
  UNIQUE (growing_profile_id, step_order)
);

CREATE TABLE requirement (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  growing_profile_id INTEGER NOT NULL REFERENCES growing_profile(id) ON DELETE CASCADE,
  category TEXT NOT NULL CHECK (category IN ('light', 'water', 'temp', 'soil_ph', 'nutrients', 'spacing', 'harvest')),
  value_min REAL,
  value_max REAL,
  unit TEXT,
  notes TEXT
);

CREATE TABLE resource (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  category TEXT,
  description TEXT
);

CREATE TABLE growing_profile_resource (
  growing_profile_id INTEGER NOT NULL REFERENCES growing_profile(id) ON DELETE CASCADE,
  resource_id INTEGER NOT NULL REFERENCES resource(id) ON DELETE CASCADE,
  quantity_notes TEXT,
  PRIMARY KEY (growing_profile_id, resource_id)
);

CREATE TABLE hazard (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  description TEXT,
  mitigation_summary TEXT,
  kind TEXT NOT NULL DEFAULT 'food_safety' CHECK (kind IN ('food_safety', 'growing_issue'))
);

CREATE TABLE growing_profile_hazard (
  growing_profile_id INTEGER NOT NULL REFERENCES growing_profile(id) ON DELETE CASCADE,
  hazard_id INTEGER NOT NULL REFERENCES hazard(id) ON DELETE CASCADE,
  mitigation_detail TEXT,
  evidence_notes TEXT,
  PRIMARY KEY (growing_profile_id, hazard_id)
);

CREATE TABLE source (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  url TEXT,
  publisher TEXT,
  year INTEGER,
  source_type TEXT NOT NULL CHECK (source_type IN ('peer_review', 'extension', 'grey_literature', 'community'))
);

CREATE TABLE citation (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id INTEGER NOT NULL REFERENCES source(id) ON DELETE CASCADE,
  target_type TEXT NOT NULL CHECK (target_type IN ('profile', 'step', 'hazard')),
  target_id INTEGER NOT NULL,
  quote TEXT,
  page TEXT
);

CREATE TABLE calendar_task (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  growing_profile_id INTEGER NOT NULL REFERENCES growing_profile(id) ON DELETE CASCADE,
  week_offset INTEGER,
  season TEXT,
  task TEXT NOT NULL,
  priority TEXT CHECK (priority IN ('low', 'medium', 'high'))
);

CREATE TABLE plant_relationship (
  plant_a_id INTEGER NOT NULL REFERENCES plant(id) ON DELETE CASCADE,
  plant_b_id INTEGER NOT NULL REFERENCES plant(id) ON DELETE CASCADE,
  relationship_type TEXT NOT NULL,
  notes TEXT,
  PRIMARY KEY (plant_a_id, plant_b_id),
  CHECK (plant_a_id < plant_b_id)
);

CREATE INDEX idx_growing_profile_plant ON growing_profile(plant_id);
CREATE INDEX idx_growing_profile_env ON growing_profile(environment_condition_id);
CREATE INDEX idx_growing_profile_medium ON growing_profile(medium_id);
CREATE INDEX idx_citation_target ON citation(target_type, target_id);
