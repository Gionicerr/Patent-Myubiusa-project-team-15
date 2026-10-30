package ru.russtech.parking.ui

import android.os.Looper
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import ru.russtech.parking.network.*
import java.time.Instant
import java.util.concurrent.CompletableFuture

/** Fake API only; neither server persistence nor a real device is certified here. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class NetworkParkingViewModelTest {
    private val vehicle = "11111111-1111-4111-8111-111111111111"
    private val obj = "22222222-2222-4222-8222-222222222222"
    private val row = ServerSession("33333333-3333-4333-8333-333333333333", vehicle, obj, "2035-01-01T00:00:00Z", "2035-01-01T01:00:00Z", "active", 1, false)
    private fun idle() { shadowOf(Looper.getMainLooper()).idle() }
    private fun <T> failed(status: Int): CompletableFuture<T> = CompletableFuture<T>().apply { completeExceptionally(ParkingFailure(status)) }
    private inner class FakeApi : ParkingApi {
        var rows = emptyList<ServerSession>(); var mutationError: Int? = null; var readError: Int? = null
        var closed = false; var reads = 0; val actions = mutableListOf<SessionAction>()
        override fun vehicles(token: String) = CompletableFuture.completedFuture(listOf(ServerVehicle(vehicle, obj, "UNIT", "Unit")))
        override fun objects(token: String) = CompletableFuture.completedFuture(listOf(ServerObject(obj, "source-unit", "Object")))
        override fun sessions(token: String, vehicleId: String): CompletableFuture<List<ServerSession>> {
            reads++; return readError?.let { failed(it) } ?: CompletableFuture.completedFuture(rows)
        }
        override fun mutate(token: String, action: SessionAction): CompletableFuture<ServerSession> {
            actions.add(action)
            return mutationError?.let { failed(it) } ?: CompletableFuture.completedFuture(rows.first())
        }
        override fun close() { closed = true }
    }
    private fun connected(api: FakeApi): NetworkParkingViewModel {
        val model = NetworkParkingViewModel(RuntimeEnvironment.getApplication())
        model.apiFactory = { _, _ -> api }; model.connect("http://127.0.0.1:18881", "unit-only"); idle()
        assertTrue(model.state.connected); assertNull(model.state.vehicleId) // Explicit choice is mandatory.
        model.selectVehicle(vehicle); idle(); model.selectObject(obj)
        return model
    }
    @Test fun `uncertain mutation keeps same action until explicit retry`() {
        val api = FakeApi(); val model = connected(api)
        api.mutationError = 0; model.create(Instant.now().plusSeconds(3600).toString()); idle()
        val pending = requireNotNull(model.state.pending)
        assertTrue(model.state.mustRefresh); assertEquals(1, api.actions.size)
        model.create(Instant.now().plusSeconds(7200).toString()); assertEquals(1, api.actions.size)
        api.mutationError = null; api.rows = listOf(row); model.retryPending(); idle()
        assertEquals(pending, api.actions.last()); assertNull(model.state.pending)
        assertEquals(listOf(row), model.state.sessions); model.disconnect()
    }
    @Test fun `409 requires successful reread before another confirmation`() {
        val api = FakeApi().apply { rows = listOf(row) }; val model = connected(api); model.selectSession(row.id)
        api.mutationError = 409; api.readError = 503
        model.confirm(Instant.now().plusSeconds(3600).toString()); idle()
        assertTrue(model.state.mustRefresh); assertNull(model.state.pending)
        val calls = api.actions.size; model.confirm(Instant.now().plusSeconds(3600).toString()); assertEquals(calls, api.actions.size)
        api.readError = null; api.rows = listOf(row.copy(revision = 2)); model.refreshSessions(); idle()
        assertFalse(model.state.mustRefresh); model.selectSession(row.id)
        api.mutationError = null; model.confirm(Instant.now().plusSeconds(3600).toString()); idle()
        assertEquals(2L, org.json.JSONObject(api.actions.last().body).getLong("expectedRevision")); model.disconnect()
    }
    @Test fun `network mode does not persist tokens or invoke the demo repository`() {
        val app = RuntimeEnvironment.getApplication()
        val preferences = app.getSharedPreferences("parking_demo", 0); preferences.edit().putString("snapshot", "preserve-offline").commit()
        val api = FakeApi(); val model = connected(api); model.disconnect()
        assertTrue(api.closed); assertFalse(model.state.connected); assertNull(model.state.pending)
        assertEquals("preserve-offline", preferences.getString("snapshot", null))
    }
}
