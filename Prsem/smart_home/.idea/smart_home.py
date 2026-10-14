
import random
import time
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable


class DeviceRepository:

    def __init__(self):
        self._devices: Dict[str, 'Device'] = {}
        self._event_log: List[dict] = []

    def add_device(self, device: 'Device') -> None:
        self._devices[device.id] = device

    def get_device(self, device_id: str) -> Optional['Device']:
        return self._devices.get(device_id)

    def get_all_devices(self) -> List['Device']:
        return list(self._devices.values())

    def get_devices_by_room(self, room: str) -> List['Device']:
        return [d for d in self._devices.values() if d.room == room]

    def update_device_value(self, device_id: str, value: float) -> None:
        if device_id in self._devices:
            self._devices[device_id].value = value

    def update_device_status(self, device_id: str, status: str) -> None:
        if device_id in self._devices:
            self._devices[device_id].status = status

    def log_event(self, event: dict) -> None:
        event['timestamp'] = datetime.now().isoformat(timespec='seconds')
        self._event_log.append(event)

    def get_logs(self, limit: int = 20) -> List[dict]:
        return self._event_log[-limit:]

@dataclass
class Device:
    id: str
    name: str
    type: str
    room: str
    value: float = 0.0
    status: str = "off"
    unit: str = ""

    def __str__(self):
        if self.type == "sensor":
            return f"[{self.id}] {self.name} ({self.room}) = {self.value}{self.unit}"
        return f"[{self.id}] {self.name} ({self.room}) — {self.status.upper()}"


@dataclass
class Rule:
    name: str
    condition: Callable[[dict], bool]
    action: Callable[[], None]
    enabled: bool = True


class RulesEngine:

    def __init__(self, repo: DeviceRepository):
        self.repo = repo
        self.rules: List[Rule] = []
        self._register_default_rules()

    def _register_default_rules(self) -> None:
        self.rules.append(Rule(
            name="Свет при движении",
            condition=lambda data: data.get('motion') == 1,
            action=lambda: self.repo.update_device_status("light_1", "on")
        ))
        self.rules.append(Rule(
            name="Свет выключить, если нет движения",
            condition=lambda data: data.get('motion') == 0,
            action=lambda: self.repo.update_device_status("light_1", "off")
        ))
        self.rules.append(Rule(
            name="Кондиционер при жаре (>26°C)",
            condition=lambda data: data.get('temperature', 0) > 26,
            action=lambda: self.repo.update_device_status("ac_1", "on")
        ))
        self.rules.append(Rule(
            name="Кондиционер выключить при комфорте (<22°C)",
            condition=lambda data: data.get('temperature', 0) < 22,
            action=lambda: self.repo.update_device_status("ac_1", "off")
        ))
        self.rules.append(Rule(
            name="Сигнализация при протечке",
            condition=lambda data: data.get('leak') == 1,
            action=lambda: self.repo.update_device_status("alarm_1", "on")
        ))
        self.rules.append(Rule(
            name="Увлажнитель при сухости (<30%)",
            condition=lambda data: data.get('humidity', 100) < 30,
            action=lambda: self.repo.update_device_status("humidifier_1", "on")
        ))

    def process_telemetry(self, telemetry: dict) -> List[str]:
        triggered = []

        for key, value in telemetry.items():
            device = self.repo.get_device(key)
            if device and device.type == "sensor":
                self.repo.update_device_value(key, value)
                self.repo.log_event({
                    "type": "telemetry",
                    "device": key,
                    "value": value
                })

        for rule in self.rules:
            if not rule.enabled:
                continue
            try:
                if rule.condition(telemetry):
                    rule.action()
                    triggered.append(rule.name)
                    self.repo.log_event({
                        "type": "rule_triggered",
                        "rule": rule.name
                    })
            except Exception as e:
                self.repo.log_event({
                    "type": "rule_error",
                    "rule": rule.name,
                    "error": str(e)
                })

        return triggered


class SmartHomeService:

    def __init__(self, repo: DeviceRepository, engine: RulesEngine):
        self.repo = repo
        self.engine = engine

    def get_all_devices(self) -> List[Device]:
        return self.repo.get_all_devices()

    def get_device_info(self, device_id: str) -> str:
        device = self.repo.get_device(device_id)
        if not device:
            return f"❌ Устройство '{device_id}' не найдено."
        return str(device)

    def control_device(self, device_id: str, command: str) -> str:
        device = self.repo.get_device(device_id)
        if not device:
            return f"❌ Устройство '{device_id}' не найдено."
        if device.type != "actuator":
            return f"⚠️ Устройство '{device_id}' не является исполнительным."

        if command not in ("on", "off"):
            return f"⚠️ Неизвестная команда: {command}. Используйте 'on' или 'off'."

        self.repo.update_device_status(device_id, command)
        self.repo.log_event({
            "type": "manual_control",
            "device": device_id,
            "command": command
        })
        return f"✅ {device.name} переключено в режим {command.upper()}."

    def handle_telemetry(self, telemetry: dict) -> List[str]:
        return self.engine.process_telemetry(telemetry)

    def get_history(self, limit: int = 20) -> List[dict]:
        return self.repo.get_logs(limit)

    def get_rules(self) -> List[str]:
        return [f"{'🟢' if r.enabled else '🔴'} {r.name}" for r in self.engine.rules]


class ConsoleUI:

    def __init__(self, service: SmartHomeService):
        self.service = service

    def run(self) -> None:
        self._print_header()
        self._init_devices()

        while True:
            self._print_menu()
            choice = input("👉 Выберите действие: ").strip()

            if choice == "1":
                self._show_devices()
            elif choice == "2":
                self._manual_control()
            elif choice == "3":
                self._simulate_sensors()
            elif choice == "4":
                self._show_history()
            elif choice == "5":
                self._show_rules()
            elif choice == "6":
                print("\n👋 До свидания!")
                break
            else:
                print("⚠️ Неверный ввод. Попробуйте снова.")


    def _print_header(self) -> None:
        print("=" * 60)
        print("   🏠  SMART HOME HUB — Система управления умным домом")
        print("=" * 60)

    def _print_menu(self) -> None:
        print("\n" + "─" * 60)
        print("📋 ГЛАВНОЕ МЕНЮ")
        print("─" * 60)
        print("1. 📊 Показать все устройства")
        print("2. 🎛️  Управлять устройством вручную")
        print("3. 📡 Симулировать событие (датчики)")
        print("4. 📜 Показать историю событий")
        print("5. ⚙️  Показать активные правила")
        print("6. 🚪 Выход")
        print("─" * 60)

    def _init_devices(self) -> None:
        repo = self.service.repo

        repo.add_device(Device("motion", "Датчик движения", "sensor", "Гостиная", 0, unit=""))
        repo.add_device(Device("temperature", "Датчик температуры", "sensor", "Гостиная", 22.0, unit="°C"))
        repo.add_device(Device("humidity", "Датчик влажности", "sensor", "Гостиная", 45.0, unit="%"))
        repo.add_device(Device("leak", "Датчик протечки", "sensor", "Ванная", 0, unit=""))

        repo.add_device(Device("light_1", "Свет в гостиной", "actuator", "Гостиная"))
        repo.add_device(Device("ac_1", "Кондиционер", "actuator", "Гостиная"))
        repo.add_device(Device("alarm_1", "Сигнализация", "actuator", "Ванная"))
        repo.add_device(Device("humidifier_1", "Увлажнитель", "actuator", "Гостиная"))

        print("✅ Устройства инициализированы (8 шт.)")

    def _show_devices(self) -> None:
        print("\n📊 СПИСОК УСТРОЙСТВ")
        print("─" * 60)
        devices = self.service.get_all_devices()
        if not devices:
            print("   (нет устройств)")
            return
        for d in devices:
            icon = "🔹" if d.type == "sensor" else "🔸"
            print(f"  {icon} {d}")
        print("─" * 60)

    def _manual_control(self) -> None:
        print("\n🎛️  РУЧНОЕ УПРАВЛЕНИЕ")
        device_id = input("   Введите ID устройства (например, light_1): ").strip()
        command = input("   Введите команду (on/off): ").strip().lower()
        result = self.service.control_device(device_id, command)
        print(f"   {result}")

    def _simulate_sensors(self) -> None:
        print("\n📡 СИМУЛЯЦИЯ ДАТЧИКОВ")
        print("   Генерируем случайные данные...")

        telemetry = {
            "motion": random.choice([0, 0, 1, 1]),          # 50% вероятность движения
            "temperature": round(random.uniform(15, 35), 1),
            "humidity": round(random.uniform(20, 70), 1),
            "leak": random.choice([0, 0, 0, 1]),            # 25% вероятность протечки
        }

        print(f"   📥 Телеметрия: {telemetry}")
        triggered = self.service.handle_telemetry(telemetry)

        if triggered:
            print(f"\n   ⚡ Сработали правила:")
            for rule in triggered:
                print(f"      • {rule}")
        else:
            print("   ℹ️  Правила не сработали.")

        print("\n   📊 Текущее состояние исполнительных устройств:")
        for d in self.service.get_all_devices():
            if d.type == "actuator":
                print(f"      • {d.name}: {d.status.upper()}")

    def _show_history(self) -> None:
        print("\n📜 ИСТОРИЯ СОБЫТИЙ (последние 15)")
        print("─" * 60)
        logs = self.service.get_history(limit=15)
        if not logs:
            print("   (история пуста)")
        else:
            for log in logs:
                t = log.get('timestamp', '')
                if log['type'] == 'telemetry':
                    print(f"  [{t}] 📥 {log['device']} = {log['value']}")
                elif log['type'] == 'rule_triggered':
                    print(f"  [{t}] ⚡ Правило: {log['rule']}")
                elif log['type'] == 'manual_control':
                    print(f"  [{t}] 🎛️  {log['device']} -> {log['command']}")
                elif log['type'] == 'rule_error':
                    print(f"  [{t}] ❌ Ошибка правила: {log['rule']}")
        print("─" * 60)

    def _show_rules(self) -> None:
        print("\n⚙️  АКТИВНЫЕ ПРАВИЛА АВТОМАТИЗАЦИИ")
        print("─" * 60)
        for rule in self.service.get_rules():
            print(f"   {rule}")
        print("─" * 60)

if __name__ == "__main__":
    repo = DeviceRepository()

    engine = RulesEngine(repo)

    service = SmartHomeService(repo, engine)

    ui = ConsoleUI(service)
    ui.run()