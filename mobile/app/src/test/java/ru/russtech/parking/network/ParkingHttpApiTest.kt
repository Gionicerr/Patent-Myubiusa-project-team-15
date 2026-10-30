package ru.russtech.parking.network

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.IOException
import java.time.Instant
import java.util.concurrent.ExecutionException
import java.util.concurrent.TimeUnit

/** Fake HTTP replies only. These tests never certify device/server integration. */
class ParkingHttpApiTest {
    private val vehicle = "11111111-1111-4111-8111-111111111111"
    private val obj = "22222222-2222-4222-8222-222222222222"
    private val session = "33333333-3333-4333-8333-333333333333"
    private val end = "2035-01-01T12:00:00Z"
    private val now = Instant.parse("2035-01-01T10:00:00Z")
    private fun sessionJson(revision: Long = 1) = JSONObject().put("id", session).put("vehicleId", vehicle)
        .put("objectId", obj).put("routeId", JSONObject.NULL).put("startedAt", "2035-01-01T10:00:00.123456+00:00")
        .put("endAt", "2035-01-01T12:00:00.123456+00:00").put("revision", revision)
        .put("status", "active").put("paymentConfirmed", false).toString()
    private fun sessionDto(revision: Long = 1) = ServerSession(session, vehicle, obj, "2035-01-01T10:00:00Z", end, "active", revision, false)
    private fun page(items: JSONArray, page: Int = 1, total: Int = items.length()) =
        JSONObject().put("items", items).put("page", page).put("pageSize", 50).put("total", total).toString()

    @Test fun `HTTP is debug local only and credential-bearing origins are rejected`() {
        assertEquals("127.0.0.1", ParkingHttpApi.origin("http://127.0.0.1:18881", true).host)
        assertEquals("10.0.2.2", ParkingHttpApi.origin("http://10.0.2.2:18881", true).host)
        for (url in listOf("http://example.invalid", "https://user:password@example.invalid", "https://example.invalid/api", "https://example.invalid?token=test")) {
            assertTrue(runCatching { ParkingHttpApi.origin(url, true) }.isFailure)
        }
        assertTrue(runCatching { ParkingHttpApi.origin("http://127.0.0.1:18881", false) }.isFailure)
        assertEquals("https", ParkingHttpApi.origin("https://example.invalid", false).scheme)
    }
    @Test fun `GET runs asynchronously and traverses contract pages`() {
        val caller = Thread.currentThread(); val paths = mutableListOf<String>()
        val row = JSONObject().put("id", vehicle).put("driverId", obj).put("registration", "UNIT").put("displayName", "Unit")
        val transport = HttpTransport { _, path, method, token, body ->
            assertNotEquals(caller, Thread.currentThread()); assertEquals("GET", method); assertNull(body)
            assertEquals("unit-only", token); paths.add(path)
            WireReply(200, page(JSONArray().put(row), if ("page=2" in path) 2 else 1, 2))
        }
        ParkingHttpApi("http://127.0.0.1:18881", true, transport).use { api ->
            assertEquals(2, api.vehicles("unit-only").get(5, TimeUnit.SECONDS).size)
            assertEquals(listOf("/api/vehicles?page=1&pageSize=50", "/api/vehicles?page=2&pageSize=50"), paths)
        }
    }
    @Test fun `objects use spb and sessions use the API UUID`() {
        val paths = mutableListOf<String>()
        ParkingHttpApi("http://127.0.0.1:18881", true, HttpTransport { _, path, _, _, _ ->
            paths.add(path); WireReply(200, page(JSONArray()))
        }).use { api ->
            api.objects("unit-only").get(5, TimeUnit.SECONDS); api.sessions("unit-only", vehicle).get(5, TimeUnit.SECONDS)
            assertEquals(listOf("/api/parking-objects?city=spb&page=1&pageSize=50", "/api/vehicles/$vehicle/sessions?page=1&pageSize=50"), paths)
        }
        assertTrue(runCatching { SessionAction.create("demo-a", obj, end, now) }.isFailure)
    }
    @Test fun `uncertain create retry keeps exact body key and target`() {
        val action = SessionAction.create(vehicle, obj, end, now); val bodies = mutableListOf<String?>()
        ParkingHttpApi("http://127.0.0.1:18881", true, HttpTransport { _, path, method, _, body ->
            assertEquals(action.path, path); assertEquals("POST", method); bodies.add(body)
            if (bodies.size == 1) throw IOException("unit simulated timeout")
            WireReply(201, sessionJson())
        }).use { api ->
            try { api.mutate("unit-only", action).get(5, TimeUnit.SECONDS); fail("expected uncertain outcome") }
            catch (e: ExecutionException) { assertEquals(0, (e.cause as ParkingFailure).status) }
            val row = api.mutate("unit-only", action).get(5, TimeUnit.SECONDS)
            assertEquals(bodies[0], bodies[1]); assertEquals("2035-01-01T12:00:00.123456+00:00", row.endAt)
            val json = JSONObject(action.body)
            assertEquals(setOf("objectId", "endAt", "idempotencyKey"), json.keySet())
            assertEquals("2035-01-01T12:00:00Z", json.getString("endAt"))
            assertNotEquals(json.getString("idempotencyKey"), JSONObject(SessionAction.create(vehicle, obj, end, now).body).getString("idempotencyKey"))
        }
    }
    @Test fun `confirmation takes expected revision from the loaded server record`() {
        val action = SessionAction.confirm(sessionDto(7), end, now); val json = JSONObject(action.body)
        assertEquals(setOf("endAt", "expectedRevision", "idempotencyKey"), json.keySet())
        assertEquals(7L, json.getLong("expectedRevision")); assertEquals("/api/sessions/$session/confirm", action.path)
        val next = JSONObject(SessionAction.confirm(sessionDto(8), end, now).body)
        assertEquals(8L, next.getLong("expectedRevision")); assertNotEquals(json.getString("idempotencyKey"), next.getString("idempotencyKey"))
    }
    @Test fun `HTTP failures are safe and never cause implicit retries or demo responses`() {
        for (status in listOf(401, 403, 409, 422, 503)) {
            var calls = 0
            ParkingHttpApi("http://127.0.0.1:18881", true, HttpTransport { _, _, _, _, _ -> calls++; WireReply(status, "RAW_PRIVATE_BODY") }).use { api ->
                try { api.mutate("unit-only", SessionAction.confirm(sessionDto(), end, now)).get(5, TimeUnit.SECONDS); fail() }
                catch (e: ExecutionException) {
                    val error = e.cause as ParkingFailure; assertEquals(status, error.status)
                    assertFalse(failureMessage(error).contains("RAW_PRIVATE_BODY")); assertEquals(status >= 500, error.uncertain)
                }
                assertEquals(1, calls)
            }
        }
    }
    @Test fun `malformed successful mutation is uncertain rather than accepted`() {
        ParkingHttpApi("http://127.0.0.1:18881", true, HttpTransport { _, _, _, _, _ -> WireReply(201, "{}") }).use { api ->
            try { api.mutate("unit-only", SessionAction.create(vehicle, obj, end, now)).get(5, TimeUnit.SECONDS); fail() }
            catch (e: ExecutionException) { assertTrue((e.cause as ParkingFailure).uncertain) }
        }
    }
    @Test fun `past endAt is rejected for a new action`() {
        assertTrue(runCatching { SessionAction.create(vehicle, obj, "2000-01-01T00:00:00Z", now) }.isFailure)
    }
}
