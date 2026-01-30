from pathlib import Path

PKG_DIR = Path(__file__).parent
DATA_DIR = PKG_DIR / "data"
PIPELINES_DIR = DATA_DIR / "pipelines"
PROMPTS_DIR = DATA_DIR / "prompts"
SEED_DIR = DATA_DIR / "seed"
SKETCH_TEMPLATES_DIR = DATA_DIR / "sketch_templates"
INGESTION_PLAN_TEMPLATE = DATA_DIR / "ingestion_plan_template.json"
AGENT_TIERS_PATH = DATA_DIR / "agent_tiers.json"
PROCESS_HINTS_PATH = DATA_DIR / "process_hints.json"
AGENT_REVIEW_PROMPTS_DIR = PROMPTS_DIR / "agent_review"
