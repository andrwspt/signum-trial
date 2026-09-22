"""v12 Integration Tests — full pipeline verification."""
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage import (
    open_db, migrate_v11_to_v12, save_document, get_document,
    save_typed_link, get_chunk_links, strengthen_link, decay_links,
    record_chunk_access, decay_activations, get_hot_chunks,
    chunk_to_document_sync, detect_conflicts, cos,
    save_note, save_chunks, get_chunks
)


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test_v12.db")
    with open_db(db_path) as conn:
        migrate_v11_to_v12(conn)
    return db_path


def test_document_crud(db):
    with open_db(db) as conn:
        did = save_document(conn, '/test.md', '# Hello\nWorld')
        doc = get_document(conn, did)
        assert doc['path'] == '/test.md'
        assert doc['version'] == 1
        assert 'Hello' in doc['content']


def test_document_versioning(db):
    with open_db(db) as conn:
        did = save_document(conn, '/v.md', 'v1')
        doc1 = get_document(conn, did)
        assert doc1['version'] == 1
        
        # Same content → no new version
        did2 = save_document(conn, '/v.md', 'v1')
        assert did2 == did
        doc2 = get_document(conn, did)
        assert doc2['version'] == 1
        
        # Different content → new version
        did3 = save_document(conn, '/v.md', 'v2')
        doc3 = get_document(conn, did)
        assert doc3['version'] == 2


def test_chunk_sync_basic(db):
    with open_db(db) as conn:
        did = save_document(conn, '/sync.md', 'First paragraph.\nSecond paragraph.\nThird paragraph.')
        
        # Create chunk with correct offsets
        start = len('First paragraph.\n')
        end = start + len('Second paragraph.')
        conn.execute(
            'INSERT INTO chunks (id, text, note_id, source_doc_id, source_offset_start, source_offset_end, created, start, end) VALUES (?,?,?,?,?,?,?,?,?)',
            ('c_sync', 'Second paragraph.', 'note1', did, start, end, '2026-01-01T00:00:00', 0, 0)
        )
        
        # Edit chunk
        result = chunk_to_document_sync(conn, 'c_sync', 'UPDATED second paragraph.')
        assert result == True
        
        doc = get_document(conn, did)
        expected = 'First paragraph.\nUPDATED second paragraph.\nThird paragraph.'
        assert doc['content'] == expected


def test_chunk_sync_shifts_offsets(db):
    with open_db(db) as conn:
        did = save_document(conn, '/shift.md', 'One.\nTwo.\nThree.')
        
        # Create two chunks
        conn.execute(
            'INSERT INTO chunks (id, text, note_id, source_doc_id, source_offset_start, source_offset_end, created, start, end) VALUES (?,?,?,?,?,?,?,?,?)',
            ('c1', 'One.', 'n1', did, 0, 4, '2026-01-01T00:00:00', 0, 0)
        )
        conn.execute(
            'INSERT INTO chunks (id, text, note_id, source_doc_id, source_offset_start, source_offset_end, created, start, end) VALUES (?,?,?,?,?,?,?,?,?)',
            ('c2', 'Three.', 'n1', did, 8, 14, '2026-01-01T00:00:00', 0, 0)
        )
        
        # Edit first chunk (grows)
        chunk_to_document_sync(conn, 'c1', 'One with more text.')
        
        # Second chunk should have shifted
        c2 = conn.execute('SELECT * FROM chunks WHERE id = ?', ('c2',)).fetchone()
        assert c2['source_offset_start'] > 8  # shifted right
        assert c2['source_offset_end'] > 14


def test_typed_links(db):
    with open_db(db) as conn:
        save_typed_link(conn, 'a', 'b', 'supports', 0.8)
        save_typed_link(conn, 'b', 'c', 'contrasts', 0.6)
        save_typed_link(conn, 'c', 'a', 'causes', 0.7)
        
        links = get_chunk_links(conn, 'a', 'outgoing')
        assert len(links) == 1
        assert links[0]['link_type'] == 'supports'
        assert links[0]['weight'] == 0.8
        
        links = get_chunk_links(conn, 'a', 'incoming')
        assert len(links) == 1
        assert links[0]['link_type'] == 'causes'


def test_strengthen_link(db):
    with open_db(db) as conn:
        save_typed_link(conn, 'x', 'y', 'supports', 0.5)
        strengthen_link(conn, 'x', 'y', 0.2)
        links = get_chunk_links(conn, 'x')
        assert abs(links[0]['weight'] - 0.7) < 0.01


def test_decay_links(db):
    with open_db(db) as conn:
        save_typed_link(conn, 'x', 'y', 'supports', 0.5)
        decay_links(conn, 0.1)
        links = get_chunk_links(conn, 'x')
        assert abs(links[0]['weight'] - 0.4) < 0.01


def test_activation_access(db):
    with open_db(db) as conn:
        conn.execute(
            'INSERT INTO chunks (id, text, note_id, activation, created, start, end) VALUES (?,?,?,?,?,?,?)',
            ('c_act', 'test', 'n1', 0.5, '2026-01-01T00:00:00', 0, 0)
        )
        record_chunk_access(conn, 'c_act')
        hot = get_hot_chunks(conn, 5)
        assert hot[0]['activation'] > 0.5


def test_decay_activations(db):
    with open_db(db) as conn:
        conn.execute(
            'INSERT INTO chunks (id, text, note_id, activation, created, start, end) VALUES (?,?,?,?,?,?,?)',
            ('c_dec', 'test', 'n1', 0.5, '2026-01-01T00:00:00', 0, 0)
        )
        decay_activations(conn, 0.1)
        hot = get_hot_chunks(conn, 5)
        assert hot[0]['activation'] == 0.4


def test_pinned_no_decay(db):
    with open_db(db) as conn:
        conn.execute(
            'INSERT INTO chunks (id, text, note_id, activation, pinned, created, start, end) VALUES (?,?,?,?,?,?,?,?)',
            ('c_pin', 'test', 'n1', 0.5, True, '2026-01-01T00:00:00', 0, 0)
        )
        decay_activations(conn, 0.1)
        hot = get_hot_chunks(conn, 5)
        assert hot[0]['activation'] == 0.5  # pinned, no decay


def test_conflict_detection(db):
    with open_db(db) as conn:
        # Create two contradictory chunks with different vectors (same topic, negation flip)
        vec_a = str([0.1] * 384)
        vec_b = str([0.1001] * 384)  # slightly different for similarity < 1.0
        conn.execute(
            'INSERT INTO chunks (id, text, note_id, vector, created, start, end) VALUES (?,?,?,?,?,?,?)',
            ('c_pos', 'ML is very effective', 'n1', vec_a, '2026-01-01T00:00:00', 0, 0)
        )
        conn.execute(
            'INSERT INTO chunks (id, text, note_id, vector, created, start, end) VALUES (?,?,?,?,?,?,?)',
            ('c_neg', 'ML is not very effective', 'n1', vec_b, '2026-01-01T00:00:00', 0, 0)
        )
        conflicts = detect_conflicts(conn, 'c_pos', threshold=0.85)
        assert len(conflicts) > 0


def test_no_conflict_similar_content(db):
    with open_db(db) as conn:
        vec = str([0.1] * 384)
        conn.execute(
            'INSERT INTO chunks (id, text, note_id, vector, created, start, end) VALUES (?,?,?,?,?,?,?)',
            ('c_a', 'ML works well.', 'n1', vec, '2026-01-01T00:00:00', 0, 0)
        )
        conn.execute(
            'INSERT INTO chunks (id, text, note_id, vector, created, start, end) VALUES (?,?,?,?,?,?,?)',
            ('c_b', 'ML works great.', 'n1', vec, '2026-01-01T00:00:00', 0, 0)
        )
        conflicts = detect_conflicts(conn, 'c_a', threshold=0.85)
        assert len(conflicts) == 0  # similar, not contradictory


def test_tenant_isolation(db):
    with open_db(db) as conn:
        conn.execute(
            'INSERT INTO chunks (id, text, note_id, tenant_id, created, start, end) VALUES (?,?,?,?,?,?,?)',
            ('c_t1', 'secret', 'n1', 'team_a', '2026-01-01T00:00:00', 0, 0)
        )
        conn.execute(
            'INSERT INTO chunks (id, text, note_id, tenant_id, created, start, end) VALUES (?,?,?,?,?,?,?)',
            ('c_t2', 'other', 'n1', 'team_b', '2026-01-01T00:00:00', 0, 0)
        )
        a_chunks = conn.execute('SELECT id FROM chunks WHERE tenant_id = ?', ('team_a',)).fetchall()
        assert len(a_chunks) == 1
        assert a_chunks[0]['id'] == 'c_t1'


def test_dynamics_log(db):
    with open_db(db) as conn:
        conn.execute(
            'INSERT INTO chunks (id, text, note_id, created, start, end) VALUES (?,?,?,?,?,?)',
            ('c_log', 'test', 'n1', '2026-01-01T00:00:00', 0, 0)
        )
        from storage import log_dynamics
        log_dynamics(conn, 'c_log', 'access', 0.5, 0.6)
        logs = conn.execute('SELECT * FROM dynamics_log WHERE chunk_id = ?', ('c_log',)).fetchall()
        assert len(logs) == 1
        assert logs[0]['event_type'] == 'access'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
