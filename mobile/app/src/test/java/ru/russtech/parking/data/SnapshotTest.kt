package ru.russtech.parking.data

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import ru.russtech.parking.domain.*

class SnapshotTest {
    private fun sample(): ParkingState {
        val engine = DemoParkingEngine(ParkingState(1_800_000_000_000))
        engine.nextPosition(); engine.startSession(30); engine.advanceMinutes(20)
        return engine.state
    }
    @Test fun `roundtrip retains every field and deduplication flag`() {
        val state = sample()
        assertEquals(state, SnapshotCodec.decode(SnapshotCodec.encode(state)))
    }
    @Test fun `empty state roundtrip retains nullable fields`() {
        val state = ParkingState(1_800_000_000_000)
        assertEquals(state, SnapshotCodec.decode(SnapshotCodec.encode(state)))
    }
    @Test fun `incompatible snapshot version is rejected`() {
        val data = JSONObject(SnapshotCodec.encode(sample())).put("version", 2)
        assertThrows(IllegalArgumentException::class.java) { SnapshotCodec.decode(data.toString()) }
    }
    @Test fun `invalid route index is rejected`() {
        val data = JSONObject(SnapshotCodec.encode(sample())).put("pointIndex", 10000)
        assertThrows(IllegalArgumentException::class.java) { SnapshotCodec.decode(data.toString()) }
    }
    @Test fun `payment cannot silently become confirmed through a saved snapshot`() {
        val data = JSONObject(SnapshotCodec.encode(sample()))
        data.getJSONArray("sessions").getJSONObject(0).put("paymentConfirmed", true)
        assertThrows(IllegalArgumentException::class.java) { SnapshotCodec.decode(data.toString()) }
    }
    @Test fun `unknown object is rejected`() {
        val data = JSONObject(SnapshotCodec.encode(sample()))
        data.getJSONArray("sessions").getJSONObject(0).put("objectId", "unknown")
        assertThrows(IllegalArgumentException::class.java) { SnapshotCodec.decode(data.toString()) }
    }
}
