import jax.numpy as jnp
from multipledispatch import dispatch

from ..gps import ConjugatePosterior, NonConjugatePosterior, Posterior
from ..kernels import Kernel, initialise
from ..likelihoods import Likelihood, initialise
from ..mean_functions import MeanFunction, initialise
from ..utils import concat_dictionaries, merge_dictionaries


def _initialise_hyperparams(kernel: Kernel, meanf: MeanFunction) -> dict:
    return concat_dictionaries(initialise(kernel), initialise(meanf))


@dispatch(ConjugatePosterior)
def initialise(gp: ConjugatePosterior) -> dict:
    hyps = _initialise_hyperparams(gp.prior.kernel, gp.prior.mean_function)
    return concat_dictionaries(hyps, initialise(gp.likelihood))


@dispatch(ConjugatePosterior, object)
def initialise(gp: ConjugatePosterior, n_data):
    return initialise(gp)


@dispatch(NonConjugatePosterior, int)
def initialise(gp: NonConjugatePosterior, n_data: int) -> dict:
    hyperparams = _initialise_hyperparams(gp.prior.kernel, gp.prior.mean_function)
    likelihood = concat_dictionaries(hyperparams, initialise(gp.likelihood))
    latent_process = {"latent": jnp.zeros(shape=(n_data, 1))}
    return concat_dictionaries(likelihood, latent_process)


def complete(params: dict, gp: Posterior, n_data: int = None) -> dict:
    full_param_set = initialise(gp, n_data)
    return merge_dictionaries(full_param_set, params)