package ru.russtech.parking.domain

import org.junit.Assert.*
import org.junit.Test

class RepositoryTest {
    private class MemoryStore : StateStore {
        var value: ParkingState? = null
        var failWrite = false
        override fun load() = value
        override fun save(state: ParkingState) { check(!failWrite) { "Storage full" }; value = state }
    }
    @Test fun `restart restores route session events and demo clock without new charges or events`() {
        val store = MemoryStore(); val first = DemoRepository(store) { 1_800_000_000_000 }
        first.nextPosition(); first.startSession(30); first.advanceMinutes(20)
        val before = first.state(); val second = DemoRepository(store) { 1_900_000_000_000 }
        assertEquals(before, second.state())
        second.advanceMinutes(1)
        assertEquals(1, second.state().events.count { it.type == "warning_10_minutes" })
        assertFalse(requireNotNull(second.state().activeSession).paymentConfirmed)
    }
    @Test fun `failed write leaves the last published state intact`() {
        val store = MemoryStore(); val repository = DemoRepository(store) { 1_800_000_000_000 }
        repository.nextPosition(); val before = repository.state(); store.failWrite = true
        assertThrows(IllegalStateException::class.java) { repository.startSession(30) }
        assertEquals(before, repository.state()); assertEquals(before, store.value)
    }
    @Test fun `unreadable checkpoint is preserved until explicit reset`() {
        var written = false
        val store = object : StateStore {
            override fun load(): ParkingState? = error("Corrupted snapshot")
            override fun save(state: ParkingState) { written = true }
        }
        val repository = DemoRepository(store) { 1_800_000_000_000 }
        assertNotNull(repository.restoreWarning)
        assertThrows(IllegalStateException::class.java) { repository.nextPosition() }
        assertFalse(written)
        repository.reset(); assertTrue(written); assertNull(repository.restoreWarning)
        repository.nextPosition(); assertEquals(1, repository.state().pointIndex)
    }
    @Test fun `payment adapter is explicitly unavailable and cannot mark session paid`() {
        val repository = DemoRepository(MemoryStore()) { 1_800_000_000_000 }
        repository.nextPosition(); repository.startSession(30)
        val before = repository.state(); val link = repository.paymentLink()
        assertEquals("unavailable", link.mode); assertNull(link.url); assertFalse(link.paymentConfirmed)
        assertEquals(before, repository.state())
    }
    @Test fun `reset clears only demo state and is persisted`() {
        val store = MemoryStore(); val repository = DemoRepository(store) { 1_800_000_000_000 }
        repository.nextPosition(); repository.startSession(30); repository.reset()
        assertTrue(repository.state().sessions.isEmpty()); assertTrue(repository.state().events.isEmpty())
        assertEquals(0, repository.state().pointIndex); assertEquals(repository.state(), store.value)
    }
}
