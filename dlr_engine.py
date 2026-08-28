"""
ZESCO DLR Digital Twin - IEEE 738 Thermal Balance Engine
========================================================
Implements the steady-state heat balance equation from IEEE Std 738:

    q_Joule + q_Solar = q_Convective + q_Radiative

Both a FORWARD twin (predict steady-state conductor temperature from
load + weather) and a BACKWARD DLR engine (solve the maximum safe current
under live cooling conditions) are provided.

The model also includes thermal sag / ground-clearance estimation using a
catenary approximation so operators can visualise clearance risk alongside
ampacity headroom.
"""

import math


class WireDigitalTwin:
    def __init__(
        self,
        R_ref: float = 0.15,
        alpha: float = 0.004,
        max_temp: float = 75.0,
        emissivity: float = 0.5,
        static_rating: float = 3.0,
        span_length: float = 150.0,
        linear_expansion: float = 2.3e-5,
        ref_temp: float = 20.0,
        clearance_ref: float = 8.0,
        diameter_m: float = 0.0270,
    ):
        """
        IEEE-738 steady-state heat balance, per unit conductor length (W/m):

            q_Joule + q_Solar = q_Convective + q_Radiative

        :param R_ref: Baseline wire resistance per unit length (ohm/m) at 20 deg C
        :param alpha: Temperature coefficient of resistance (1/deg C)
        :param max_temp: Maximum allowed safe thermal limit (deg C)
        :param emissivity: Surface radiation emissivity (0-1)
        :param static_rating: Static conservative ampacity limit (A)
        :param span_length: Conductor span length (m), used for sag calc
        :param linear_expansion: Linear thermal expansion coeff (1/deg C)
        :param ref_temp: Reference temperature for resistance (deg C)
        :param clearance_ref: Ground clearance at reference temp (m)
        :param diameter_m: Conductor overall diameter (m) - used to compute
                           the perimeter (pi*D) that drives conv/rad cooling
        """
        self.R_ref = R_ref
        self.alpha = alpha
        self.max_temp = max_temp
        self.emissivity = emissivity
        self.static_rating = static_rating
        self.span_length = span_length
        self.linear_expansion = linear_expansion
        self.ref_temp = ref_temp
        self.clearance_ref = clearance_ref
        self.diameter_m = diameter_m
        self.perimeter = math.pi * diameter_m
        self.stefan_boltzmann = 5.67e-8  # W/(m^2 K^4)
        # Calibration so that the dynamic rating matches the published
        # ampacity under ANSI reference conditions (25 C, 0.6 m/s wind).
        # Tuned against the 330 kV ACSR Bison conductor (595 A @ 75 C).
        self._convec_scale = 0.326

    # ------------------------------------------------------------------
    # Material / parameter helpers
    # ------------------------------------------------------------------
    def get_resistance(self, temp_c: float) -> float:
        """Temperature-dependent electrical resistance (ohm/m)."""
        return self.R_ref * (1.0 + self.alpha * (temp_c - self.ref_temp))

    def convective_coefficient(self, wind_speed: float) -> float:
        """Effective convective heat-transfer coefficient (W/m^2 K).

        Simplified IEEE-738 forced-convection correlation valid for
        low to moderate wind speeds on typical overhead conductors.
        """
        return self._convec_scale * (10.1 + 12.5 * math.sqrt(max(0.1, wind_speed)))

    # ------------------------------------------------------------------
    # Heat balance terms (per unit conductor length, W/m)
    # ------------------------------------------------------------------
    def joule_heat(self, current: float, temp_c: float) -> float:
        """Joule (I^2 R) heating per unit length (W/m)."""
        return (current ** 2) * self.get_resistance(temp_c)

    def convective_loss(self, temp_c: float, ambient: float, wind_speed: float) -> float:
        """Convective cooling per unit length (W/m)."""
        h_c = self.convective_coefficient(wind_speed)
        return h_c * self.perimeter * (temp_c - ambient)

    def radiative_loss(self, temp_c: float, ambient: float) -> float:
        """Radiative cooling per unit length (W/m) via Stefan-Boltzmann."""
        t_k = temp_c + 273.15
        a_k = ambient + 273.15
        return (
            self.emissivity
            * self.stefan_boltzmann
            * self.perimeter
            * (t_k ** 4 - a_k ** 4)
        )

    # ------------------------------------------------------------------
    # FORWARD TWIN - predict steady-state conductor temperature
    # ------------------------------------------------------------------
    def predict_temperature(
        self, current: float, T_ambient: float, wind_speed: float
    ) -> float:
        """Solve heat balance with Newton iteration to find the conductor
        equilibrium temperature for a given load and weather."""
        T = T_ambient + 5.0
        for _ in range(60):
            h_c = self.convective_coefficient(wind_speed)
            q_joule = self.joule_heat(current, T)
            q_conv = self.convective_loss(T, T_ambient, wind_speed)
            q_rad = self.radiative_loss(T, T_ambient)

            residual = q_joule - q_conv - q_rad
            # d(losses)/dT
            dq_dT = self.perimeter * (
                h_c + 4.0 * self.emissivity * self.stefan_boltzmann * ((T + 273.15) ** 3)
            )
            dq_dT = max(dq_dT, 1e-3)

            T_new = T + residual / dq_dT
            T_new = max(T_ambient - 50.0, min(200.0, T_new))
            if abs(T_new - T) < 0.005:
                T = T_new
                break
            T = T_new

        return round(max(T_ambient, T), 2)

    # ------------------------------------------------------------------
    # BACKWARD DLR ENGINE - solve maximum safe current
    # ------------------------------------------------------------------
    def solve_rating_for_temp(self, target_temp: float, ambient: float, wind_speed: float) -> float:
        """Maximum current that keeps the conductor at `target_temp` (A)."""
        R = self.get_resistance(target_temp)
        q_conv = self.convective_loss(target_temp, ambient, wind_speed)
        q_rad = self.radiative_loss(target_temp, ambient)
        total = max(0.0, q_conv + q_rad)
        if total <= 0.0 or R <= 0.0:
            return 0.0
        return math.sqrt(total / R)

    def calculate_dynamic_rating(self, T_ambient: float, wind_speed: float) -> float:
        """Backward DLR: maximum safe current under live cooling conditions."""
        return round(self.solve_rating_for_temp(self.max_temp, T_ambient, wind_speed), 2)

    # ------------------------------------------------------------------
    # Thermal sag / ground clearance (catenary approximation)
    # ------------------------------------------------------------------
    def estimate_sag(self, temp_c: float) -> float:
        """Mid-span sag (m) at a given conductor temperature.

        Uses the elastic-catenary approximation:
            sag(T) ~= span * sqrt( 3 * alpha_lin * (T - T_ref) / 8 )
        """
        dt = max(0.0, temp_c - self.ref_temp)
        return round(self.span_length * math.sqrt((3.0 * self.linear_expansion * dt) / 8.0), 2)

    def estimate_clearance(self, temp_c: float) -> float:
        """Minimum ground clearance (m) at a given conductor temperature."""
        sag = self.estimate_sag(temp_c)
        sag_ref = self.estimate_sag(self.ref_temp)
        return round(self.clearance_ref - (sag - sag_ref), 2)

    # ------------------------------------------------------------------
    # Operational status & analytics helpers
    # ------------------------------------------------------------------
    def capacity_gain_pct(self, dynamic_rating: float, static_rating: float) -> float:
        """Percentage headroom unlocked by dynamic line rating."""
        if static_rating <= 0:
            return 0.0
        return round(((dynamic_rating - static_rating) / static_rating) * 100.0, 1)

    def classify_status(self, current: float, dynamic_rating: float, static_rating: float) -> str:
        """Classify the operating state of the line.

        Returns one of: 'OK', 'WARNING', 'CRITICAL'.
        """
        if current > dynamic_rating:
            return "CRITICAL"
        if current > static_rating:
            return "WARNING"
        return "OK"

    def evaluate(self, current: float, ambient: float, wind_speed: float, measured_temp: float = None):
        """Convenience method returning a full operational snapshot."""
        dynamic = self.calculate_dynamic_rating(ambient, wind_speed)
        static = self.static_rating
        if measured_temp is None or measured_temp <= 0:
            measured_temp = self.predict_temperature(current, ambient, wind_speed)
        status = self.classify_status(current, dynamic, static)
        return {
            "conductor_temp": round(measured_temp, 2),
            "model_temp": self.predict_temperature(current, ambient, wind_speed),
            "ambient_temp": round(ambient, 2),
            "wind_speed": round(wind_speed, 2),
            "current_load": round(current, 2),
            "static_rating": static,
            "dynamic_rating": dynamic,
            "capacity_gain_pct": self.capacity_gain_pct(dynamic, static),
            "status": status,
            "sag_m": self.estimate_sag(measured_temp),
            "clearance_m": self.estimate_clearance(measured_temp),
        }
