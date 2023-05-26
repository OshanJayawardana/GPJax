import abc
from dataclasses import dataclass
from functools import partial

from beartype.typing import (
    Callable,
    List,
    Optional,
    Type,
    Union,
)
import jax.numpy as jnp
from jaxtyping import Float, Num, Array
import tensorflow_probability.substrates.jax.distributions as tfd

from gpjax.base import (
    Module,
    param_field,
    static_field,
)

import reduce as red
from .. import kernels


@dataclass
class RkhsVec(Module):
    insp_pts: Union["RkhsVec", Float[Array, "N M ..."]]
    k: kernels.AbstractKernel = param_field(kernels.RBF())
    reduce: red.Reduce = param_field(red.Identity())
    transpose: bool = False

    @property
    def T(self):
        return RkhsVec(
            self.insp_pts,
            self.k,
            self.reduce,
            transpose=not self.transpose,
        )

    # Todo: __getitem__ methods, including slicing, indexing, and boolean indexing.

    @property
    def is_colvec(self) -> bool:
        return not self.transpose

    @property
    def is_rowvec(self) -> bool:
        return self.transpose

    @property
    def shape(self):
        if self.transpose:
            return (1, self.size)
        return (self.size, 1)

    @property
    def size(self):
        return self.reduce.final_len(len(self.insp_pts))

    def __len__(self):
        if self.transpose:
            return 1
        else:
            return self.size

    def __pairwise_dot__(self, other: "RkhsVec") -> Float[Array, "N M"]:
        """Compute the dot product between all pairs of elements from two RKHS vectors.

        Args:
            other (RkhsVec): The other RKHS vector. Assumed to have the same kernel.

        Raises:
            TypeError: If the kernels of the two RKHS vectors do not match.

        Returns:
            Float[Array]: A matrix of shape (self.size, other.size) containing the dot products.
        """
        if self.k != other.k:
            raise TypeError(
                f"Trying to compute inner products between elements of different RKHSs (Kernel types do not match)"
            )
        raw_gram = self.k.cross_covariance(self.insp_pts, other.insp_pts)
        return self.reduce @ (other.reduce @ raw_gram.T).T

    def __tensor_prod__(self, other: "RkhsVec") -> "RkhsVec":
        if self.size != other.size:
            raise ValueError(
                f"Trying to compute tensor product between RKHS vectors of different sizes ({self.size} and {other.size})"
            )
        return ProductVec([self, other], red.Sum())

    def sum(
        self,
    ) -> "RkhsVec":
        return red.Sum() @ self

    def mean(
        self,
    ) -> "RkhsVec":
        return red.Mean() @ self

    def __matmul__(self, other: "RkhsVec") -> Union[Float[Array, "M N"], "RkhsVec"]:
        if self.is_rowvec == other.is_rowvec:
            raise ValueError(
                f"Trying to compute matrix product between two row vectors or two column vectors"
            )
        if self.is_rowvec and other.is_colvec:
            # this returns a matrix with the RKHS inner products between all pairs of elements of self and other
            return self.__pairwise_dot__(other)
        elif self.is_colvec and other.is_rowvec:
            # this returns a RKHS vector with the tensor product between all pairs of elements of self and other
            return self.__tensor_prod__(other)
        else:
            raise ValueError(
                f"Trying to compute matrix product between two RKHS vectors of the same ({self.shape}). This is not supported."
            )

    def __rmatmul__(
        self, other: Union[red.AbstractReduce, "RkhsVec"]
    ) -> Union[Float[Array, "M N"], "RkhsVec"]:
        if isinstance(other, red.AbstractReduce):
            return RkhsVec(self.insp_pts, self.k, other @ self.reduce, self.transpose)
        else:
            return self.__matmul__(other)

    def __add__(self, other: "RkhsVec") -> "RkhsVec":
        return SumVec([self, other])

    def __mul__(self, other: "RkhsVec") -> "RkhsVec":
        return ProductVec([self, other])


@dataclass
class CombinationVec(RkhsVec):
    rkhs_vecs: List[RkhsVec]
    operator: Callable = static_field(None)
    reduce: red.Reduce = param_field(red.NoReduce())

    def __post_init__(self):
        orig_len = len(self.rkhs_vecs[0])
        for rkhs_vec in self.rkhs_vecs:
            if len(rkhs_vec) != orig_len:
                raise ValueError(
                    f"Trying to combine RKHS vectors of different sizes ({orig_len} and {len(rkhs_vec)})"
                )
        self.__len = self.reduce.new_len(orig_len)

    @property
    def insp_pts(self):
        return jnp.concatenate([rkhs_vec.insp_pts for rkhs_vec in self.rkhs_vecs])

    @property
    def size(self):
        return self.__len


SumVec = partial(CombinationVec, operator=jnp.add)
ProductVec = partial(CombinationVec, operator=jnp.multiply)
