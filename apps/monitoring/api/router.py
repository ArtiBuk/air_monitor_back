from ninja import Router

from .routers.datasets import router as datasets_router
from .routers.experiments import router as experiments_router
from .routers.forecasts import router as forecasts_router
from .routers.models import router as models_router
from .routers.observations import router as observations_router
from .routers.overview import router as overview_router
from .routers.tasks import router as tasks_router

router = Router()
router.add_router("", overview_router)
router.add_router("", observations_router)
router.add_router("", datasets_router)
router.add_router("", models_router)
router.add_router("", forecasts_router)
router.add_router("", experiments_router)
router.add_router("", tasks_router)
