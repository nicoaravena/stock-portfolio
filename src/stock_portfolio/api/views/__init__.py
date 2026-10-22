from ninja import NinjaAPI
from pydantic import ValidationError as PydanticValidationError

from ._exceptions import Conflict
from .portfolios import router as portfolio_router
from .stocks import router as stock_router

api = NinjaAPI(title="Stock Portfolio")
api.add_router("/portfolios", portfolio_router)
api.add_router("/stocks", stock_router)


@api.exception_handler(Conflict)
def _conflict(request, exc):
    return api.create_response(request, {"detail": str(exc)}, status=409)


@api.exception_handler(ValueError)
@api.exception_handler(PydanticValidationError)
def _domain_error(request, exc):
    return api.create_response(request, {"detail": str(exc)}, status=422)
