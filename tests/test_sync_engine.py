from sync_engine import SyncEngine, _upsert_entity, EntityStats
from notion_props import rich_text, title
from trimble_client import DeviceRecord, MachineRecord, ProjectRecord, TrimbleSnapshot


class FakeNotion:
    def __init__(self):
        self.created = []
        self.updated = []

    def create_page(self, data_source_id, properties):
        self.created.append((data_source_id, properties))
        return {"id": "new"}

    def update_page(self, page_id, properties):
        self.updated.append((page_id, properties))
        return {"id": page_id}


class FakeIndexEntry:
    def __init__(self, page_id, properties):
        self.page_id = page_id
        self.properties = properties


def test_create_vs_update_decisions():
    notion = FakeNotion()
    stats = EntityStats()
    index = {}
    props = {
        "Name": title("Alpha"),
        "Trimble Project ID": rich_text("pid-1"),
    }

    _upsert_entity(
        notion,
        data_source_id="ds",
        stable_property="Trimble Project ID",
        stable_id="pid-1",
        properties=props,
        compare_keys=("Name", "Trimble Project ID"),
        index=index,
        dry_run=False,
        stats=stats,
        label="Alpha",
    )
    assert stats.created == 1
    assert len(notion.created) == 1

    index["pid-1"] = FakeIndexEntry("page-1", props)
    _upsert_entity(
        notion,
        data_source_id="ds",
        stable_property="Trimble Project ID",
        stable_id="pid-1",
        properties=props,
        compare_keys=("Name", "Trimble Project ID"),
        index=index,
        dry_run=False,
        stats=stats,
        label="Alpha",
    )
    assert stats.unchanged == 1
    assert len(notion.updated) == 0


def test_dry_run_prevents_writes():
    notion = FakeNotion()
    stats = EntityStats()
    props = {"Name": title("Beta"), "Trimble Device ID": rich_text("dev-1")}
    _upsert_entity(
        notion,
        data_source_id="ds",
        stable_property="Trimble Device ID",
        stable_id="dev-1",
        properties=props,
        compare_keys=("Name", "Trimble Device ID"),
        index={},
        dry_run=True,
        stats=stats,
        label="Beta",
    )
    assert stats.created == 1
    assert notion.created == []


def test_stable_id_matching_no_duplicate_create():
    notion = FakeNotion()
    stats = EntityStats()
    index = {"mid-1": FakeIndexEntry("p1", {"Trimble Machine ID": rich_text("mid-1")})}
    props = {"Name": title("M1"), "Trimble Machine ID": rich_text("mid-1")}
    _upsert_entity(
        notion,
        data_source_id="ds",
        stable_property="Trimble Machine ID",
        stable_id="mid-1",
        properties=props,
        compare_keys=("Name", "Trimble Machine ID"),
        index=index,
        dry_run=False,
        stats=stats,
        label="M1",
    )
    assert stats.created == 0
    assert len(notion.created) == 0


def test_missing_optional_trimble_fields():
    record = DeviceRecord(device_id="d1", name="D1")
    assert record.latitude is None
    assert record.project_name == ""


class FakeNotionEngine(FakeNotion):
    def index_by_rich_text(self, data_source_id, property_name):
        return {}

    def verify_data_source(self, data_source_id):
        return "ok"


def test_engine_counts_trimble_records():
    engine = SyncEngine(
        FakeNotionEngine(),
        projects_ds="p",
        devices_ds="d",
        machines_ds="m",
        dry_run=True,
    )
    snapshot = TrimbleSnapshot(
        account_id="acct",
        projects=[ProjectRecord("p1", "1587-RMV")],
        devices=[DeviceRecord("d1", "Tab")],
        machines=[MachineRecord("m1", "Dozer")],
        devices_with_project_assignment=1,
    )
    summary = engine.run(snapshot)
    assert summary.trimble_projects == 1
    assert summary.projects.created == 1
    assert summary.devices.created == 1
    assert summary.machines.created == 1
