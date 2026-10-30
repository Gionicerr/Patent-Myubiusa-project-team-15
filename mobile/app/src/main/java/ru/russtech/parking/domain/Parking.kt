package ru.russtech.parking.domain

import java.util.UUID

/** Local demonstration domain. These objects are NOT authoritative parking/tariff zones. */
data class DemoObject(val id: String, val label: String, val latitude: Double, val longitude: Double)
enum class MatchState { MATCHED, NO_MATCH, NO_COORDINATES, TECHNICAL_ERROR, AMBIGUOUS, STALE }
data class RoutePoint(val latitude: Double?, val longitude: Double?, val state: MatchState, val objectId: String?, val caption: String)
data class ParkingSession(
    val id: String, val objectId: String, val startedAt: Long, val endAt: Long,
    val revision: Int = 1, val expired: Boolean = false, val warned: Boolean = false,
    val paymentConfirmed: Boolean = false
)
data class ParkingEvent(val id: String, val type: String, val occurredAt: Long, val message: String, val sessionId: String? = null)
data class ParkingState(
    val now: Long, val pointIndex: Int = 0, val stableObjectId: String? = null,
    val sessions: List<ParkingSession> = emptyList(), val events: List<ParkingEvent> = emptyList()
) {
    val point: RoutePoint get() = DemoRoute.points[pointIndex]
    val activeSession: ParkingSession? get() = sessions.lastOrNull { !it.expired }
}
object DemoRoute {
    val objects = listOf(
        DemoObject("demo-a", "Демо-объект А", 59.9340, 30.3310),
        DemoObject("demo-b", "Демо-объект Б", 59.9355, 30.3340)
    )
    // Synthetic points and match outcomes, not an import of spb.json or a production matcher.
    val points = listOf(
        RoutePoint(59.9320, 30.3280, MatchState.NO_MATCH, null, "Начало маршрута: совпадения нет"),
        RoutePoint(59.9340, 30.3310, MatchState.MATCHED, "demo-a", "Въезд к демо-объекту А"),
        RoutePoint(59.9345, 30.3315, MatchState.MATCHED, "demo-a", "Движение внутри расчётной области А"),
        RoutePoint(59.9355, 30.3340, MatchState.MATCHED, "demo-b", "Переход к демо-объекту Б"),
        RoutePoint(59.9370, 30.3370, MatchState.NO_MATCH, null, "Выезд: зона не определена"),
        RoutePoint(null, null, MatchState.NO_COORDINATES, null, "Координаты не получены"),
        RoutePoint(null, null, MatchState.TECHNICAL_ERROR, null, "Техническая ошибка геолокации"),
        RoutePoint(59.9348, 30.3325, MatchState.AMBIGUOUS, null, "Неоднозначное совпадение"),
        RoutePoint(59.9348, 30.3325, MatchState.STALE, null, "Устаревшее наблюдение"),
        RoutePoint(59.9340, 30.3310, MatchState.MATCHED, "demo-a", "Координаты восстановлены: объект А")
    )
    fun objectById(id: String?) = objects.find { it.id == id }
}

/** Same driver operations can later be implemented by a verified server adapter. */
interface ParkingRepository {
    fun state(): ParkingState
    fun nextPosition(): ParkingState
    fun startSession(minutes: Int): ParkingState
    fun confirmSession(minutes: Int): ParkingState
    fun advanceMinutes(minutes: Int): ParkingState
    fun paymentLink(): PaymentLink
    fun reset(): ParkingState
}
data class PaymentLink(val url: String? = null, val mode: String = "unavailable", val paymentConfirmed: Boolean = false)

class DemoParkingEngine(initial: ParkingState) {
    var state = initial
        private set
    private fun event(type: String, message: String, sessionId: String? = null) {
        val entry = ParkingEvent(UUID.randomUUID().toString(), type, state.now, message, sessionId)
        state = state.copy(events = (state.events + entry).takeLast(500))
    }
    fun nextPosition(): ParkingState {
        check(state.pointIndex < DemoRoute.points.lastIndex) { "Маршрут завершён. Можно сбросить демонстрацию." }
        val oldId = state.stableObjectId
        state = state.copy(pointIndex = state.pointIndex + 1)
        val point = state.point
        when (point.state) {
            MatchState.MATCHED -> {
                if (point.objectId != oldId) {
                    state = state.copy(stableObjectId = point.objectId)
                    event(if (oldId == null) "entry" else "object_changed",
                        if (oldId == null) "Вы въехали в расчётную область ${DemoRoute.objectById(point.objectId)?.label}. Проверьте необходимость оплаты."
                        else "Объект изменился. Проверьте необходимость новой оплаты. Текущая сессия сохранена.")
                }
            }
            MatchState.NO_MATCH -> {
                state = state.copy(stableObjectId = null)
                if (oldId != null) event("exit", "Вы покинули текущую расчётную область. Сессия сохранена; отсутствие совпадения не означает бесплатную парковку.")
            }
            MatchState.NO_COORDINATES, MatchState.TECHNICAL_ERROR -> event("location_error", point.caption + ". Сессия сохранена.")
            MatchState.AMBIGUOUS, MatchState.STALE -> Unit // Never turn uncertainty into a confirmed exit.
        }
        return state
    }
    private fun endAt(minutes: Int): Long {
        require(minutes in 1..1440) { "Укажите от 1 до 1440 минут." }
        return state.now + minutes * 60_000L
    }
    fun startSession(minutes: Int): ParkingState {
        check(state.activeSession == null) { "Уже есть активная сессия. Подтвердите её время вместо создания новой." }
        check(state.point.state == MatchState.MATCHED) { "Сначала требуется однозначно определённый объект." }
        val session = ParkingSession(UUID.randomUUID().toString(), requireNotNull(state.point.objectId), state.now, endAt(minutes))
        state = state.copy(sessions = (state.sessions + session).takeLast(100))
        event("session_started", "Сессия запущена. Оплата не подтверждена.", session.id)
        evaluateTime()
        return state
    }
    fun confirmSession(minutes: Int): ParkingState {
        val active = checkNotNull(state.activeSession) { "Нет активной сессии." }
        val updated = active.copy(endAt = endAt(minutes), revision = active.revision + 1, warned = false)
        state = state.copy(sessions = state.sessions.map { if (it.id == active.id) updated else it })
        event("session_confirmed", "Время сессии подтверждено. Это не подтверждение оплаты.", active.id)
        evaluateTime()
        return state
    }
    fun advanceMinutes(minutes: Int): ParkingState {
        require(minutes in 1..1440) { "Укажите от 1 до 1440 минут." }
        state = state.copy(now = state.now + minutes * 60_000L)
        evaluateTime()
        return state
    }
    private fun evaluateTime() {
        val active = state.activeSession ?: return
        val remaining = active.endAt - state.now
        when {
            remaining <= 0 -> {
                state = state.copy(sessions = state.sessions.map { if (it.id == active.id) it.copy(expired = true) else it })
                event("session_expired", "Время парковочной сессии истекло. Проверьте необходимость оплаты.", active.id)
            }
            remaining <= 10 * 60_000 && !active.warned -> {
                state = state.copy(sessions = state.sessions.map { if (it.id == active.id) it.copy(warned = true) else it })
                event("warning_10_minutes", "До окончания сессии осталось не более 10 минут.", active.id)
            }
        }
    }
}
