from config import microlab_config
microlab_config.validate_config()

from recipes import tasks
import pytest
import yaml
import hardware.core
from unittest.mock import MagicMock

from util.logger import MultiprocessingLogger
MultiprocessingLogger._logging_queue = MagicMock()


@pytest.fixture
def devices(request):
    simulation_devices = """devices:
  - id: "reactor-thermometer"
    type: "thermometer"
    # Type of thermometer to use for measuring the temp of the reactor
    # Supported values: w1_therm, serial, simulation
    # w1_therm: Supports the DS18S20, DS1822, DS18B20, DS28EA00 and DS1825/MAX31850K
    #           sensors using the 1 wire protocol. You'll need to add "dtoverlay=w1-gpio"
    #           to /boot/config.txt and reboot to use this on a pi, see https://github.com/libre-computer-project/libretech-wiring-tool
    #           for enabling the w1-gpio overlay on the AML-S905X-CC
    # serial: reads the sensor data from a serial device
    implementation: "simulation"
    ## serial MODE CONFIG
    # Which device to read data from.
    serialDevice: "/dev/ttyUSB0"
    temp: 42

  - id: "reactor-temperature-controller"
    type: "tempController"
    # Which temperature controller implementation to use
    # Supported values: basic, simulation
    # basic: Basic hardware setup using two sets of pumps and a heating element
    #        some currently incomplete instructions for this are in docs/assembly
    # simulation: Simulates temperature changes due to heater and cooler activation
    #             No other configuration required or possible at the moment
    implementation: "simulation"
    # device ID of the thermometer to use for detecting reactor temperature
    thermometerID: "reactor-thermometer"
    # Maximum and minimum temperature in Celsius that the hardware can support
    # The microlab v0.5 makes use of 3d printed parts made of PLA, PLA can only reach
    # ~60C before it begins to mechanically fail. If you print with a different material,
    # this may be increased, search for the glass transition temperature for your material.
    # Water of course also boils at 100C, and will slowly boil off somewhat below that
    # so consider something like Propylene Glycol instead of water as a heat exchanger fluid.
    # Also keep in mind the recommended thermometer (DS18S20) only supports -55 to 125C.
    maxTemp: 50
    minTemp: -20
    gpioID: "gpio-primary"
    # GPIO pin for activating the heating element
    heaterPin: BCM_26
    # GPIO pin for activating the heater pump(s)
    heaterPumpPin: BCM_20
    # GPIO pin for activating the cooler pump(s)
    coolerPin: BCM_21
    # list of device IDs that must be setup before this device
    dependencies: ["reactor-thermometer"]

  - id: "reactor-reagent-dispenser"
    type: "reagentDispenser"
    # Which reagent dispenser implementation to use
    # Supported values: syringepump, simulation, peristalticpump
    # syringepump: The open source syringe pump referenced in the assembly documentation
    #              Uses grbl and stepper motors to dispense the reagents into the microlab
    # simulation: Does nothing but sleep to simulate dispensing a reagent
    implementation: "simulation"
    ## syringepump MODE CONFIG
    # Serial device for communication with the Arduino
    grbl: "grbl-primary"
    # Configuration for the syringe pump motors
    syringePumpsConfig:
      X:
        # Number of mm the stepper motor moves per full revolution,
        # this is the pitch of the threaded rod
        mmPerRev: 0.8
        # Number of steps per revolution of the stepper motor, reference the documentation for the motor
        stepsPerRev: 200
        # Number of mm of movement needed to dispense 1 ml of fluid,
        # this is the length of the syringe divided by its fluid capacity
        mmPerMl: 3.5
        # Maximum speed the motor should run in mm/min
        maxMmPerMin: 240
      Y:
        # These are all the same as documented above but for the Y axis
        mmPerRev: 0.8
        stepsPerRev: 200
        mmPerMl: 3.5
        maxMmPerMin: 240
      Z:
        # These are all the same as documented above but for the Y axis
        mmPerRev: 0.8
        stepsPerRev: 200
        mmPerMl: 3.5
        maxMmPerMin: 240
    # Configuration for the peristaltic pump motors
    peristalticPumpsConfig:
      # F: max feed rate in mm/min
      F: 175
      X:
        # scaling factor based on initial calibration
        mmPerMl: 0.5555555
      Y:
        # scaling factor based on initial calibration
        mmPerMl: 0.5555555
      Z:
        # scaling factor based on initial calibration
        mmPerMl: 0.5555555
    ## simulation MODE ARGS
    # None needed or supported at the moment

  - id: "reactor-stirrer"
    type: "stirrer"
    # Which stirrer implementation to use
    # Supported values: gpio_stirrer, simulation
    # gpio_stirrer: activates the stirrer by switching a gpio pin
    # simulation: Does nothing
    implementation: "simulation"
    gpioID: "gpio-primary"
    ## gpio_stirrer MODE CONFIG
    # GPIO pin for activating the stirrer
    stirrerPin: BCM_16

    ## simulation MODE CONFIG
    # None needed or supported at the moment

"""

    devices = yaml.safe_load(simulation_devices)["devices"]
    marker = request.node.get_closest_marker("microlab_data")
    if marker:
        print("marker", marker.args)

        def recurseSettings(obj, devices):
            print("recurse ", obj)
            for key, value in obj.items():
                if isinstance(value, dict) and key in devices:
                    recurseSettings(value, devices[key])
                else:
                    devices[key] = value

        # recurseSettings(marker.args[0], devices)
        for key, value in marker.args[0].items():
            device = list(filter(lambda x: x["id"] == key, devices))[0]
            recurseSettings(value, device)
    print("devices", devices)
    return devices


@pytest.fixture
def microlab(request, devices):
    return hardware.core.MicroLabHardware(devices)


# HEATING
@pytest.mark.microlab_data({"reactor-temperature-controller": {"temp": 42}})
def test_heat_done(microlab):
    fn = tasks.heat(microlab, {"temp": 30})
    microlab.turn_heater_on = MagicMock()
    microlab.turn_heater_off = MagicMock()
    res = next(fn)
    assert microlab.turn_heater_off.called
    assert res is None


@pytest.mark.microlab_data({"reactor-temperature-controller": {"temp": 18}})
def test_heat_needed(microlab):
    fn = tasks.heat(microlab, {"temp": 30})
    microlab.turn_heater_on = MagicMock()
    microlab.turn_heater_off = MagicMock()
    res = next(fn)
    assert microlab.turn_heater_on.called
    assert not microlab.turn_heater_off.called
    assert res is not None


# COOLING
@pytest.mark.microlab_data({"reactor-temperature-controller": {"temp": 42}})
def test_cool_needed(microlab):
    fn = tasks.cool(microlab, {"temp": 30})
    microlab.turn_cooler_on = MagicMock()
    microlab.turn_cooler_off = MagicMock()
    res = next(fn)
    assert microlab.turn_cooler_on.called
    assert not microlab.turn_cooler_off.called
    assert res is not None


@pytest.mark.microlab_data({"reactor-temperature-controller": {"temp": 18}})
def test_cool_done(microlab):
    fn = tasks.cool(microlab, {"temp": 30})
    microlab.turn_cooler_on = MagicMock()
    microlab.turn_cooler_off = MagicMock()
    res = next(fn)
    assert microlab.turn_cooler_off.called
    assert res is None


# MAINTAIN HEAT


@pytest.mark.microlab_data({"reactor-temperature-controller": {"temp": 18}})
def test_maintain_heat_needed(microlab):
    fn = tasks.maintain_heat(microlab, {"temp": 30, "tolerance": 3, "time": 5})
    microlab.turn_heater_on = MagicMock()
    microlab.turn_heater_off = MagicMock()
    res = next(fn)
    assert microlab.turn_heater_on.called
    assert not microlab.turn_heater_off.called
    assert res is not None


@pytest.mark.microlab_data({"reactor-temperature-controller": {"temp": 18}})
def test_maintain_heat_within_tolerance(microlab):
    fn = tasks.maintain_heat(microlab, {"temp": 30, "tolerance": 15, "time": 5})
    microlab.turn_heater_on = MagicMock()
    microlab.turn_heater_off = MagicMock()
    res = next(fn)
    assert not microlab.turn_heater_on.called
    assert res is not None


@pytest.mark.microlab_data({"reactor-temperature-controller": {"temp": 18}})
def test_maintain_heat_time_finished(microlab):
    fn = tasks.maintain_heat(microlab, {"temp": 30, "tolerance": 15, "time": 5})
    res = next(fn)
    microlab.turn_cooler_off = MagicMock()
    microlab.turn_heater_off = MagicMock()
    microlab.uptime_seconds = MagicMock(return_value=6)
    res = next(fn)
    assert microlab.turn_cooler_off.called
    assert microlab.turn_heater_off.called
    assert res is None


# MAINTAIN COOL


@pytest.mark.microlab_data({"reactor-temperature-controller": {"temp": 40}})
def test_maintain_cool_needed(microlab):
    fn = tasks.maintain_cool(microlab, {"temp": 30, "tolerance": 3, "time": 5})
    microlab.turn_cooler_on = MagicMock()
    microlab.turn_cooler_off = MagicMock()
    res = next(fn)
    assert microlab.turn_cooler_on.called
    assert not microlab.turn_cooler_off.called
    assert res is not None


@pytest.mark.microlab_data({"reactor-temperature-controller": {"temp": 40}})
def test_maintain_cool_within_tolerance(microlab):
    fn = tasks.maintain_cool(microlab, {"temp": 30, "tolerance": 15, "time": 5})
    microlab.turn_cooler_on = MagicMock()
    microlab.turn_cooler_off = MagicMock()
    res = next(fn)
    assert not microlab.turn_cooler_on.called
    assert res is not None


@pytest.mark.microlab_data({"reactor-temperature-controller": {"temp": 40}})
def test_maintain_cool_time_finished(microlab):
    fn = tasks.maintain_cool(microlab, {"temp": 30, "tolerance": 15, "time": 5})
    res = next(fn)
    microlab.turn_cooler_off = MagicMock()
    microlab.turn_heater_off = MagicMock()
    microlab.uptime_seconds = MagicMock(return_value=6)
    res = next(fn)
    assert microlab.turn_cooler_off.called
    assert microlab.turn_heater_off.called
    assert res is None


# STIRRING


def test_stir_still_running(microlab):
    fn = tasks.stir(microlab, {"time": 5})
    microlab.turn_stirrer_on = MagicMock()
    microlab.turn_stirrer_off = MagicMock()
    res = next(fn)
    assert microlab.turn_stirrer_on.called
    assert not microlab.turn_stirrer_off.called
    assert res is not None


def test_stir_time_finished(microlab):
    fn = tasks.stir(microlab, {"time": 5})
    res = next(fn)
    microlab.turn_stirrer_off = MagicMock()
    microlab.uptime_seconds = MagicMock(return_value=6)
    res = next(fn)
    assert microlab.turn_stirrer_off.called
    assert res is None


# PUMP DISPENSE

def test_pump_x(microlab):
    fn = tasks.pump(microlab, {"pump": "X", "volume": 0.1})
    res = next(fn)
    assert res > 0
    res = next(fn)
    assert res is None


def test_pump_y(microlab):
    fn = tasks.pump(microlab, {"pump": "Y", "volume": 0.1})
    res = next(fn)
    assert res > 0
    res = next(fn)
    assert res is None


def test_pump_z(microlab):
    fn = tasks.pump(microlab, {"pump": "Z", "volume": 0.1})
    res = next(fn)
    assert res > 0
    res = next(fn)
    assert res is None


def test_pump_invalid_pump_id(microlab):
    fn = tasks.pump(microlab, {"pump": "Q", "volume": 0.1})
    with pytest.raises(ValueError):
        res = next(fn)


@pytest.mark.microlab_data({"reactor-reagent-dispenser": {"minSpeed": 0.1}})
def test_pumps_slow_dispense(microlab):
    # should dispense in 10 bursts about 10 seconds apart.
    fn = tasks.pump(microlab, {"pump": "X", "volume": 1, "time": 100})
    for i in range(0, 10):
        res = next(fn)
        assert 9 == pytest.approx(res, 0.001)
    res = next(fn)
    assert 0 == pytest.approx(res)

    res = next(fn)
    assert res is None


@pytest.mark.microlab_data({"reactor-reagent-dispenser": {"minSpeed": 1.0, "maxSpeed": 5.0}})
def test_pumps_within_speed(monkeypatch, microlab) -> None:
    """
    If desired rate is between minSpeed and maxSpeed, pump_dispense should be called once
    with the requested duration, then yield exactly one dispense_time and one final None.
    """
    # volume=5, time=5 => rate=1.0 mL/s, exactly minSpeed
    monkeypatch.setattr(
        microlab,
        "get_pump_limits",
        lambda pump_name: {"minSpeed": 1.0, "maxSpeed": 5.0}
    )
    monkeypatch.setattr(
        microlab,
        "pump_dispense",
        lambda pump_name, volume, duration: 2.5
    )
    # uptime_seconds isn't used in this branch, but define it anyway
    monkeypatch.setattr(
        microlab,
        "uptime_seconds",
        lambda: 0.0
    )

    fn = tasks.pump(microlab, {"pump": "X", "volume": 5, "time": 5})

    # 1) First yield: dispense_time returned by pump_dispense
    dispense_time = next(fn)
    assert dispense_time == pytest.approx(2.5)

    # 2) Second yield: the single `None` (completion)
    res = next(fn)
    assert res is None

    # Generator should now be exhausted
    with pytest.raises(StopIteration):
        next(fn)


@pytest.mark.microlab_data({"reactor-reagent-dispenser": {"minSpeed": 1.0, "maxSpeed": 5.0}})
def test_pumps_over_max_speed(monkeypatch, microlab) -> None:
    """
    If desired rate exceeds maxSpeed, pump_dispense should be called with duration=None,
    then yield exactly one dispense_time and one final None.
    """
    # volume=10, time=1 => rate=10 mL/s > maxSpeed=5
    monkeypatch.setattr(
        microlab,
        "get_pump_limits",
        lambda pump_name: {"minSpeed": 1.0, "maxSpeed": 5.0}
    )
    monkeypatch.setattr(
        microlab,
        "pump_dispense",
        lambda pump_name, volume, duration: 3.14
    )
    monkeypatch.setattr(
        microlab,
        "uptime_seconds",
        lambda: 0.0
    )

    fn = tasks.pump(microlab, {"pump": "X", "volume": 10, "time": 1})

    # 1) First yield: dispense_time at max speed
    dispense_time = next(fn)
    assert dispense_time == pytest.approx(3.14)

    # 2) Second yield: the single `None` (completion)
    res = next(fn)
    assert res is None

    # Generator should now be exhausted
    with pytest.raises(StopIteration):
        next(fn)


@pytest.mark.microlab_data({"reactor-reagent-dispenser": {"minSpeed": 1.0, "maxSpeed": 5.0}})
def test_pumps_without_time_uses_max_speed(monkeypatch, microlab) -> None:
    """
    If 'time' is omitted, rate defaults to maxSpeed; behavior should match the 'within-speed' branch,
    yielding exactly one dispense_time and one final None.
    """
    # Omit 'time' -> volume=5, so rate = maxSpeed = 5.0
    monkeypatch.setattr(
        microlab,
        "get_pump_limits",
        lambda pump_name: {"minSpeed": 1.0, "maxSpeed": 5.0}
    )
    monkeypatch.setattr(
        microlab,
        "pump_dispense",
        lambda pump_name, volume, duration: 1.11
    )
    monkeypatch.setattr(
        microlab,
        "uptime_seconds",
        lambda: 0.0
    )

    fn = tasks.pump(microlab, {"pump": "X", "volume": 5})

    # 1) First yield: dispense_time at max speed
    dispense_time = next(fn)
    assert dispense_time == pytest.approx(1.11)

    # 2) Second yield: single `None` (completion)
    res = next(fn)
    assert res is None

    with pytest.raises(StopIteration):
        next(fn)


@pytest.mark.microlab_data({"reactor-reagent-dispenser": {"minSpeed": 2.0, "maxSpeed": 5.0}})
def test_pumps_burst_mode_with_partial(monkeypatch, microlab) -> None:
    """
    If desired rate is below minSpeed, the function should:
      1. Dispense in repeated 1-second bursts at minSpeed,
      2. Yield (interval - exec_time) for each full burst (with exec_time=0 here),
      3. After exhausting full bursts, yield a final fractional delay for the remaining volume,
      4. Then yield exactly one None (completion).
    """
    # volume=5, time=4 => rate=1.25 < minSpeed=2.0
    monkeypatch.setattr(
        microlab,
        "get_pump_limits",
        lambda pump_name: {"minSpeed": 2.0, "maxSpeed": 5.0}
    )
    # Simulate instant execution of pump_dispense so exec_time = 0
    monkeypatch.setattr(
        microlab,
        "uptime_seconds",
        lambda: 100.0
    )
    monkeypatch.setattr(
        microlab,
        "pump_dispense",
        lambda pump_name, volume, duration=None: None
    )

    fn = tasks.pump(microlab, {"pump": "X", "volume": 5, "time": 4})

    # Compute expected interval = (minSpeed / rate) - 1 = (2.0 / 1.25) - 1 = 1.6 - 1 = 0.6
    expected_interval = (2.0 / 1.25) - 1.0  # 0.6

    # Two full bursts: dispenses 2 mL twice -> 4 mL total -> yields two intervals
    for _ in range(2):
        res = next(fn)
        assert res == pytest.approx(expected_interval, rel=1e-3)

    # Now 4 mL has been dispensed; remaining = 1 mL
    # Final fractional wait = remaining / rate = 1 / 1.25 = 0.8
    final_fractional = next(fn)
    assert final_fractional == pytest.approx(0.8, rel=1e-3)

    # Next: single None (completion)
    res = next(fn)
    assert res is None

    # Generator should now be exhausted
    with pytest.raises(StopIteration):
        next(fn)


# MAINTAIN PID

@pytest.mark.microlab_data(
    {"reactor-temperature-controller": {"pidConfig": {"P": 1, "I": 0.5, "D": 5}}}
)
def test_maintain_PID_heat_needed(microlab):
    res = None
    fn = tasks.maintain_pid(microlab, {"temp": 100, "tolerance": 3, "time": 60})
    microlab.turn_heater_pump_on = MagicMock()
    microlab.turn_heater_pump_off = MagicMock()
    for i in range(0, 9):
        res = next(fn)
    microlab.turn_heater_on = MagicMock()
    microlab.turn_heater_off = MagicMock()
    microlab.turn_cooler_on = MagicMock()
    microlab.turn_cooler_off = MagicMock()
    for i in range(0, 9):
        res = next(fn)

    assert not microlab.turn_cooler_on.called
    assert microlab.turn_cooler_off.called

    assert microlab.turn_heater_pump_on.called
    assert not microlab.turn_heater_pump_off.called

    assert microlab.turn_heater_on.call_count > microlab.turn_heater_off.call_count

    assert res is not None


@pytest.mark.microlab_data(
    {
        "reactor-temperature-controller": {
            "pidConfig": {"P": 1, "I": 0.5, "D": 5},
            "temp": 100,  # starting temperature
        }
    }
)
def test_maintain_PID_cool_needed(microlab):
    res = None
    fn = tasks.maintain_pid(microlab, {"temp": 40, "tolerance": 3, "time": 60})
    microlab.turn_heater_pump_on = MagicMock()
    microlab.turn_heater_pump_off = MagicMock()
    for i in range(0, 19):
        res = next(fn)
    microlab.turn_heater_on = MagicMock()
    microlab.turn_heater_off = MagicMock()
    microlab.turn_cooler_on = MagicMock()
    microlab.turn_cooler_off = MagicMock()
    for i in range(0, 9):
        res = next(fn)

    assert microlab.turn_cooler_on.call_count > microlab.turn_cooler_off.call_count

    assert microlab.turn_heater_pump_on.called
    assert not microlab.turn_heater_pump_off.called

    assert not microlab.turn_heater_on.called
    assert microlab.turn_heater_off.called

    assert res is not None


@pytest.mark.microlab_data(
    {
        "reactor-temperature-controller": {
            "pidConfig": {"P": 1, "I": 0.5, "D": 5},
            "temp": 100,  # starting temperature
        }
    }
)
def test_maintain_PID_turns_on_heater_pump_at_start(microlab):
    microlab.turn_heater_pump_on = MagicMock()
    microlab.turn_heater_pump_off = MagicMock()
    fn = tasks.maintain_pid(microlab, {"temp": 40, "tolerance": 3, "time": 60})
    res = next(fn)
    assert microlab.turn_heater_pump_on.called
    assert not microlab.turn_heater_pump_off.called
    assert res is not None


@pytest.mark.microlab_data(
    {
        "reactor-temperature-controller": {
            "pidConfig": {"P": 1, "I": 0.5, "D": 5},
            "temp": 100,  # starting temperature
        }
    }
)
def test_maintain_PID_turns_off_heater_pump_when_done(microlab):
    time_in_seconds: int = 60
    microlab.turn_heater_pump_on = MagicMock()
    microlab.turn_heater_pump_off = MagicMock()
    microlab.uptime_seconds = MagicMock(return_value=0)
    fn = tasks.maintain_pid(microlab, {"temp": 40, "tolerance": 3, "time": time_in_seconds})
    res = next(fn)

    assert microlab.turn_heater_pump_on.called
    for i in range(0, time_in_seconds - 1):
        microlab.uptime_seconds.return_value = i + 2
        res = next(fn)

    assert microlab.turn_heater_pump_on.call_count == 1
    assert microlab.turn_heater_pump_off.call_count == 1
    assert res is None


@pytest.mark.microlab_data(
    {
        "reactor-temperature-controller": {
            "pidConfig": {
                "P": 1, "I": 0.0, "D": 0.0, "maxOutput": 100, "minOutput": -100, "dutyCycleLength": 10,
                "proportionalOnMeasurement": False, "differentialOnMeasurement": True
            },
            "temp": 100,  # starting temperature
        }
    }
)
def test_maintain_PID_heat_only(microlab):
    # force PID to always request heating (e.g. current_temp >> setpoint -> positive control)
    cycle_length = microlab.get_pid_config()["dutyCycleLength"]
    microlab.get_temp = MagicMock(side_effect=[20] * 20)
    microlab.turn_heater_on = MagicMock()
    microlab.turn_cooler_on = MagicMock()
    fn = tasks.maintain_pid(microlab, {"temp": 40, "tolerance": 3, "time": 5, "type": "both"})
    next(fn)

    # run one full cycle (`dutyCycleLength` seconds)
    for _ in range(cycle_length): next(fn)

    # heater should have been toggled on, cooler never on
    assert microlab.turn_heater_on.call_count > 0
    assert not microlab.turn_cooler_on.called


@pytest.mark.microlab_data(
    {
        "reactor-temperature-controller": {
            "pidConfig": {
                "P": 1, "I": 0.0, "D": 0.0, "maxOutput": 100, "minOutput": -100, "dutyCycleLength": 10,
                "proportionalOnMeasurement": False, "differentialOnMeasurement": True
            },
            "temp": 100,  # starting temperature
        }
    }
)
def test_maintain_PID_cool_only(microlab):
    # force PID to always request heating (e.g. current_temp << setpoint -> positive control)
    cycle_length = microlab.get_pid_config()["dutyCycleLength"]
    microlab.get_temp = MagicMock(side_effect=[60] * 20)
    microlab.turn_heater_on = MagicMock()
    microlab.turn_cooler_on = MagicMock()
    fn = tasks.maintain_pid(microlab, {"temp": 20, "tolerance": 3, "time": 5, "type": "both"})
    next(fn)

    # run one full cycle (`dutyCycleLength` seconds)
    for _ in range(cycle_length): next(fn)

    # cooler should have been toggled on, heater never on
    assert microlab.turn_cooler_on.call_count > 0
    assert not microlab.turn_heater_on.called


@pytest.mark.microlab_data(
    {
        "reactor-temperature-controller": {
            "pidConfig": {
                "P": 1, "I": 0.0, "D": 0.0, "maxOutput": 100, "minOutput": -100, "dutyCycleLength": 5,
                "proportionalOnMeasurement": False, "differentialOnMeasurement": True
            },
            "temp": 100,  # starting temperature
        }
    }
)
def test_no_action_if_within_tolerance(microlab):
    cycle_length = microlab.get_pid_config()["dutyCycleLength"]
    microlab.get_temp = MagicMock(return_value=100)
    microlab.turn_heater_on = MagicMock()
    microlab.turn_cooler_on = MagicMock()
    fn = tasks.maintain_pid(microlab, {"temp": 100, "tolerance": 3, "time": 2})
    next(fn)

    # run one full 5-second cycle
    for _ in range(cycle_length): next(fn)

    assert not microlab.turn_heater_on.called
    assert not microlab.turn_cooler_on.called


@pytest.mark.microlab_data(
    {
        "reactor-temperature-controller": {
            "pidConfig": {
                "P": 1, "I": 0.0, "D": 0.0, "maxOutput": 50, "minOutput": -50, "dutyCycleLength": 5,
                "proportionalOnMeasurement": False, "differentialOnMeasurement": True
            },
            "temp": 100,  # starting temperature
        }
    }
)
def test_zero_duration_terminates_immediately(microlab):
    microlab.get_temp = MagicMock(return_value=20)

    fn = tasks.maintain_pid(microlab, {"temp": 25, "tolerance": 1, "time": 0})
    vals = [next(fn) for _ in range(2)]

    assert vals[-1] is None
    with pytest.raises(StopIteration):
        next(fn)


@pytest.mark.microlab_data(
    {
        "reactor-temperature-controller": {
            "pidConfig": {
                "P": 1, "I": 0.0, "D": 0.0, "maxOutput": 100, "minOutput": -100, "dutyCycleLength": 8,
                "proportionalOnMeasurement": False, "differentialOnMeasurement": True
            },
            "temp": 50,  # starting temperature
        }
    }
)
def test_known_control_signal(monkeypatch, microlab):
    cycle_length = microlab.get_pid_config()["dutyCycleLength"]
    microlab.get_temp = MagicMock(return_value=0.0)
    microlab.turn_heater_on = MagicMock()
    microlab.turn_heater_off = MagicMock()
    microlab.turn_cooler_on = MagicMock()
    microlab.turn_cooler_off = MagicMock()

    class DummyPID:
        # stub PID(...) to return a dummy with a fixed output of 50
        def __init__(self, *args, **kw): self.components = (0, 0, 0)

        def __call__(self, temp): return 50

    monkeypatch.setattr(tasks, "PID", DummyPID)

    fn = tasks.maintain_pid(microlab, {"temp": 100, "tolerance": 1, "time": 5})
    next(fn)  # pump-on

    # one full 8-second cycle:
    for _ in range(cycle_length - 1): next(fn)

    # expected on-time = 8*(50/100) = 4 seconds
    assert microlab.turn_heater_on.call_count == 4
    assert microlab.turn_heater_off.call_count == 4
    assert microlab.turn_cooler_on.call_count == 0
    assert microlab.turn_cooler_off.call_count == cycle_length


# if __name__ == '__main__':
#     import sys
#     sys.exit(pytest.main([__file__]))
