package ru.russtech.parking.domain

interface StateStore {
    fun load(): ParkingState?
    fun save(state: ParkingState)
}
/** Persists first, publishes second: a write failure never silently advances the demo. */
class DemoRepository(private val store: StateStore, private val clock: () -> Long = System::currentTimeMillis) : ParkingRepository {
    var restoreWarning: String? = null
        private set
    private var current = try { store.load() ?: ParkingState(clock()) }
        catch (_: Exception) {
            restoreWarning = "Сохранённые данные не удалось прочитать. Они не перезаписаны. Сбросьте демонстрацию, чтобы продолжить."
            ParkingState(clock())
        }
    override fun state() = current
    private fun update(action: (DemoParkingEngine) -> ParkingState): ParkingState {
        check(restoreWarning == null) { requireNotNull(restoreWarning) }
        val next = action(DemoParkingEngine(current))
        store.save(next)
        current = next
        return current
    }
    override fun nextPosition() = update { it.nextPosition() }
    override fun startSession(minutes: Int) = update { it.startSession(minutes) }
    override fun confirmSession(minutes: Int) = update { it.confirmSession(minutes) }
    override fun advanceMinutes(minutes: Int) = update { it.advanceMinutes(minutes) }
    override fun paymentLink() = PaymentLink() // No official URL has been approved. Never imply payment.
    override fun reset(): ParkingState {
        val fresh = ParkingState(clock())
        store.save(fresh)
        current = fresh
        restoreWarning = null
        return current
    }
}
