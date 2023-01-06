"""
Structures for storing and working with emission lines.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Sequence

import astropy.units as u
import numpy as np
import pandas as pd

from demcmc.dem import BinnedDEM, TempBins

__all__ = [
    "ContFunc",
    "ContFuncGaussian",
    "ContFuncDiscrete",
    "EmissionLine",
    "LineCollection",
]


class ContFunc(ABC):
    """
    A contribution function.
    """

    @abstractmethod
    def binned(self, temp_bins: TempBins) -> u.Quantity:
        """
        Get contribution function averaged over a number of temperature bins.

        Parameters
        ----------
        temp_bins : TempBins
            Temperature bins to get contribution function at.

        Returns
        -------
        astropy.units.Quantity
            Contribution function at given temperature bins.
        """


class ContFuncGaussian(ContFunc):
    """
    A contribution function with a Gaussian profile.

    Parameters
    ----------
    center : u.Quantity
        Center of the Gaussian contribution function.
    width : u.Quantity
        Width of the Gaussian contribution function.
    """

    def __init__(self, center: u.Quantity, width: u.Quantity):
        self.width = width
        self.center = center

        self._width_MK = self.width.to_value(u.MK)
        self._center_MK = self.center.to_value(u.MK)

    def binned(self, temp_bins: TempBins) -> u.Quantity:
        """
        Get contribution function.

        Parameters
        ----------
        temp_bins : TempBins
            Temperature bins to get contribution function at.

        Returns
        -------
        astropy.units.Quantity
            Contribution function at given temperature bins.
        """
        bins = temp_bins.bin_centers.to_value(u.MK)
        return (
            (
                np.exp(
                    -(
                        ((self._center_MK - temp_bins._bin_centers_MK) / self._width_MK)
                        ** 2
                    )
                )
            )
            * 1e6
            * u.cm**5
            / u.K
        )


@dataclass
class ContFuncDiscrete(ContFunc):
    """
    A pre-computed contribution function defined at temperature values.
    """

    temps: u.Quantity[u.K]
    values: u.Quantity[u.cm**5 / u.K]

    def __init__(self, temps: u.Quantity[u.K], values: u.Quantity[u.cm**5 / u.K]):
        if temps.ndim != 1:
            raise ValueError("temps must be a 1D quantity")
        if values.ndim != 1:
            raise ValueError("values must be a 1D quantity")
        if temps.size != values.size:
            raise ValueError("Temperatures and values must be the same size")

        self.temps = temps
        self.values = values

    def _check_bin_edges(self, temp_bins: TempBins) -> None:
        missing_ts = []
        for t in temp_bins.edges:
            if t not in self.temps:
                missing_ts.append(t)
        if len(missing_ts):
            raise ValueError(
                f"The following bin edges in temp_bins are missing from the contribution function temperature coordinates: {missing_ts}"
            )

    def binned(self, temp_bins: TempBins) -> u.Quantity[u.cm**5 / u.K]:
        self._check_bin_edges(temp_bins)

        df = pd.DataFrame(
            {
                "Temps": self.temps.to_value(u.K),
                "values": self.values.to_value(u.cm**5 / u.K),
            }
        )
        df = df.set_index("Temps")
        df["Groups"] = pd.cut(
            df.index, temp_bins.edges.to_value(u.K), include_lowest=True
        )
        means = df.groupby("Groups").mean()
        return means["values"].values * u.cm**5 / u.K


@dataclass
class EmissionLine:
    """
    A single emission line.

    Parameters
    ----------
    cont_func : ContFunc
        Contribution function.
    intensity_obs : float
        Observed intensity.
    sigma_intensity_obs : float
        Uncertainty in observed intensity.
    """

    cont_func: ContFunc
    intensity_obs: Optional[float] = None
    sigma_intensity_obs: Optional[float] = None

    def I_pred(self, dem: BinnedDEM) -> u.Quantity:
        """
        Calculate predicted intensity of a given line.

        Parameters
        ----------
        dem : BinnedDEM
            DEM.

        Returns
        -------
        astropy.units.Quantity
            Predicted intensity.
        """
        cont_func = self.cont_func.binned(dem.temp_bins)
        ret = np.sum(cont_func * dem.values * dem.temp_bins.bin_widths)
        return ret.to_value(u.dimensionless_unscaled)


@dataclass
class LineCollection:
    """
    A collection of several emission lines.

    Parameters
    ----------
    lines : Sequence[EmissionLine]
        Emission lines.
    """

    lines: Sequence[EmissionLine]
