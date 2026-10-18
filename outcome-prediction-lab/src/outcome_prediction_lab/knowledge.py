"""The clinical knowledge tables (HFRS, Charlson, Elixhauser) now live in the service, which
serves models that use them (M12; one implementation — decisions.md O29). Re-exported here so
lab code and round scripts keep working unchanged."""
from outcome_prediction.knowledge import *  # noqa: F401,F403
from outcome_prediction.knowledge import HFRS_POINTS, scores  # noqa: F401
