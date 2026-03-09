from .router    import route
from .recipe    import RecipeAgent
from .travel    import TravelAgent
from .shopping  import ShoppingAgent
from .diy       import DiyAgent
from .appliance import ApplianceAgent
from .health    import HealthAgent

AGENT_MAP = {
    "recipe":    RecipeAgent(),
    "travel":    TravelAgent(),
    "shopping":  ShoppingAgent(),
    "diy":       DiyAgent(),
    "appliance": ApplianceAgent(),
    "health":    HealthAgent(),
}
