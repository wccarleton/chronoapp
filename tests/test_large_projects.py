import pytest
from chronologer_app.projects import import_csv, new_project, dump_project, load_project, MAX_EVENTS


def database_csv(count):
    return ('id,c14_mean,c14_err,curve,label,datum\n' + ''.join(
        f'Determination {i},2500,30,intcal20,Context {i},BP1950\n' for i in range(count))).encode()


def test_ten_thousand_event_import_and_project_roundtrip():
    content = database_csv(10000)
    assert len(content) < 5 * 1024 * 1024
    imported = import_csv(content, 'database.csv')
    assert len(imported['events']) == MAX_EVENTS == 10000
    project = {**new_project(), **imported}
    assert load_project(dump_project(project)) == project


def test_database_cap_rejects_extra_event():
    with pytest.raises(ValueError, match='10000 events'):
        import_csv(database_csv(10001), 'database.csv')


def test_long_unicode_labels_can_exceed_old_five_mib_limit():
    header = 'id,c14_mean,c14_err,curve,label,datum\n'
    row = 'D' * 100 + ',2500,30,intcal20,' + '\U0001f3fa' * 120 + ',BP1950\n'
    content = (header + row * 10000).encode('utf-8')
    assert 5 * 1024 * 1024 < len(content) < 16 * 1024 * 1024
    assert len(import_csv(content, 'unicode.csv')['events']) == 10000


def test_project_cap_rejects_extra_event():
    imported = import_csv(database_csv(10000), 'database.csv')
    project = {**new_project(), **imported}
    project['events'].append(project['events'][0])
    with pytest.raises(ValueError, match='10000 records'):
        dump_project(project)
