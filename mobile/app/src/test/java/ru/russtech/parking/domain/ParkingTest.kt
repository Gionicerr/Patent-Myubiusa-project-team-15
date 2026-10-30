package ru.russtech.parking.domain

import org.junit.Assert.*
import org.junit.Test

class ParkingTest {
    private val now = 1_800_000_000_000L
    private fun engine() = DemoParkingEngine(ParkingState(now))
    private fun entered() = engine().also { it.nextPosition() }
    private fun running(minutes: Int = 30) = entered().also { it.startSession(minutes) }
    @Test fun `entry identifies test object and never creates a session`() {
        val e = entered()
        assertEquals("demo-a", e.state.stableObjectId)
        assertEquals(listOf("entry"), e.state.events.map { it.type })
        assertNull(e.state.activeSession)
    }
    @Test fun `repeated matching object does not duplicate entry`() {
        val e = entered(); e.nextPosition()
        assertEquals(1, e.state.events.count { it.type == "entry" })
    }
    @Test fun `session starts explicitly with correct end time and unpaid status`() {
        val e = running()
        val s = requireNotNull(e.state.activeSession)
        assertEquals(now + 30 * 60_000, s.endAt)
        assertEquals("demo-a", s.objectId)
        assertFalse(s.paymentConfirmed)
    }
    @Test fun `object change preserves session identity object and end time`() {
        val e = running(); val before = e.state.activeSession
        e.nextPosition(); e.nextPosition()
        assertEquals("demo-b", e.state.stableObjectId)
        assertEquals(before, e.state.activeSession)
        assertEquals(1, e.state.events.count { it.type == "object_changed" })
    }
    @Test fun `exit preserves session and does not assert free parking`() {
        val e = running(); val before = e.state.activeSession
        repeat(3) { e.nextPosition() }
        assertNull(e.state.stableObjectId); assertEquals(before, e.state.activeSession)
        assertTrue(e.state.events.last().message.contains("не означает бесплатную"))
    }
    @Test fun `coordinate error ambiguous and stale states remain distinct and preserve session`() {
        val e = running(); val before = e.state.activeSession
        repeat(4) { e.nextPosition() }; assertEquals(MatchState.NO_COORDINATES, e.state.point.state)
        e.nextPosition(); assertEquals(MatchState.TECHNICAL_ERROR, e.state.point.state)
        val events = e.state.events.size
        e.nextPosition(); assertEquals(MatchState.AMBIGUOUS, e.state.point.state)
        e.nextPosition(); assertEquals(MatchState.STALE, e.state.point.state)
        assertEquals(events, e.state.events.size); assertEquals(before, e.state.activeSession)
        assertEquals(2, e.state.events.count { it.type == "location_error" })
    }
    @Test fun `warning fires exactly at ten minutes once per revision`() {
        val e = running(); e.advanceMinutes(19)
        assertEquals(0, e.state.events.count { it.type == "warning_10_minutes" })
        e.advanceMinutes(1); e.advanceMinutes(1)
        assertEquals(1, e.state.events.count { it.type == "warning_10_minutes" })
    }
    @Test fun `expiry fires once and preserves history`() {
        val e = running(); e.advanceMinutes(30); e.advanceMinutes(5)
        assertNull(e.state.activeSession); assertTrue(e.state.sessions.single().expired)
        assertEquals(1, e.state.events.count { it.type == "session_expired" })
        assertEquals(0, e.state.events.count { it.type == "warning_10_minutes" }) // No late warning after expiry.
    }
    @Test fun `short session warns immediately and never confirms payment`() {
        val e = running(5)
        assertTrue(requireNotNull(e.state.activeSession).warned)
        assertFalse(requireNotNull(e.state.activeSession).paymentConfirmed)
    }
    @Test fun `confirm time increments revision without changing object or identity`() {
        val e = running(); e.advanceMinutes(20)
        val previous = requireNotNull(e.state.activeSession)
        e.nextPosition(); e.nextPosition(); e.confirmSession(40)
        val current = requireNotNull(e.state.activeSession)
        assertEquals(previous.id, current.id); assertEquals(previous.objectId, current.objectId)
        assertEquals(previous.revision + 1, current.revision)
        assertEquals(e.state.now + 40 * 60_000, current.endAt); assertFalse(current.paymentConfirmed)
        e.advanceMinutes(30)
        assertEquals(2, e.state.events.count { it.type == "warning_10_minutes" })
    }
    @Test fun `cannot create a second active session`() {
        val e = running(); val before = e.state
        assertThrows(IllegalStateException::class.java) { e.startSession(30) }
        assertEquals(before, e.state)
    }
    @Test fun `cannot start with no match`() {
        val e = engine()
        assertThrows(IllegalStateException::class.java) { e.startSession(30) }
        assertTrue(e.state.sessions.isEmpty())
    }
    @Test fun `duration validation does not mutate state`() {
        val e = entered(); val before = e.state
        listOf(0, -1, 1441, Int.MAX_VALUE).forEach { m ->
            assertThrows(IllegalArgumentException::class.java) { e.startSession(m) }
            assertEquals(before, e.state)
        }
        e.startSession(1440); val session = e.state
        assertThrows(IllegalArgumentException::class.java) { e.confirmSession(0) }
        assertEquals(session, e.state)
    }
    @Test fun `advance validation does not mutate state`() {
        val e = running(); val before = e.state
        assertThrows(IllegalArgumentException::class.java) { e.advanceMinutes(-1) }
        assertEquals(before, e.state)
    }
    @Test fun `new session after expiry preserves both sessions`() {
        val e = running(); e.advanceMinutes(30); e.startSession(20)
        assertEquals(2, e.state.sessions.size)
        assertTrue(e.state.sessions.first().expired); assertNotNull(e.state.activeSession)
    }
    @Test fun `route exhaustion does not silently reset or repeat events`() {
        val e = engine(); repeat(DemoRoute.points.lastIndex) { e.nextPosition() }; val before = e.state
        assertThrows(IllegalStateException::class.java) { e.nextPosition() }; assertEquals(before, e.state)
    }
}
