from ninja import NinjaAPI
from pydantic import ValidationError as PydanticValidationError

from stock_portfolio.api.services import NoPendingPlanError, PendingPlanError
from stock_portfolio.domain import NotFoundError, PortfolioError

from ._exceptions import Conflict
from .portfolios import router as portfolio_router
from .stocks import router as stock_router

api = NinjaAPI(title="Stock Portfolio")
api.add_router("/portfolios", portfolio_router)
api.add_router("/stocks", stock_router)


@api.exception_handler(Conflict)
@api.exception_handler(NoPendingPlanError)
@api.exception_handler(PendingPlanError)
def _conflict(request, exc):
    return api.create_response(request, {"detail": str(exc)}, status=409)


# Only known domain errors are mapped; anything else (a bug) stays a 500.
# Ninja picks the handler of the most specific class in the exception's MRO.
@api.exception_handler(NotFoundError)
def _not_found(request, exc):
    return api.create_response(request, {"detail": str(exc)}, status=404)


@api.exception_handler(PortfolioError)
@api.exception_handler(PydanticValidationError)
def _domain_error(request, exc):
    return api.create_response(request, {"detail": str(exc)}, status=422)
