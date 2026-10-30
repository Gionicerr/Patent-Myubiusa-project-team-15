package ru.russtech.parking.ui

import android.app.Application
import android.content.pm.ApplicationInfo
import android.os.Handler
import android.os.Looper
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import ru.russtech.parking.network.*
import java.util.concurrent.CompletableFuture
import java.util.concurrent.CompletionException

data class NetworkParkingState(
    val connected: Boolean = false, val busy: Boolean = false,
    val vehicles: List<ServerVehicle> = emptyList(), val objects: List<ServerObject> = emptyList(),
    val sessions: List<ServerSession> = emptyList(), val vehicleId: String? = null,
    val objectId: String? = null, val sessionId: String? = null,
    val mustRefresh: Boolean = true, val pending: SessionAction? = null,
    val message: String? = null, val lastSaved: ServerSession? = null
)

/** Network state is never written to LocalStateStore; demo state is not read here. */
class NetworkParkingViewModel(application: Application) : AndroidViewModel(application) {
    var state by mutableStateOf(NetworkParkingState())
        private set
    private val main = Handler(Looper.getMainLooper())
    private var api: ParkingApi? = null
    internal var apiFactory: (String, Boolean) -> ParkingApi = { endpoint, debug -> ParkingHttpApi(endpoint, debug) }
    private var token = ""
    private var epoch = 0
    private val tasks = mutableSetOf<CompletableFuture<*>>()

    fun connect(endpoint: String, value: String) {
        if (state.busy) return
        disconnect()
        if (value.isBlank() || value.any { it.isWhitespace() }) {
            state = state.copy(message = "Введите водительский токен без пробелов."); return
        }
        try {
            val debug = getApplication<Application>().applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0
            api = apiFactory(endpoint, debug)
        } catch (_: Exception) {
            state = state.copy(message = "Проверьте адрес API. Локальный HTTP разрешён только в debug для 127.0.0.1 или 10.0.2.2."); return
        }
        token = value
        catalogs()
    }
    fun disconnect() {
        epoch++; tasks.forEach { it.cancel(true) }; tasks.clear()
        api?.close(); api = null; token = ""; state = NetworkParkingState()
    }
    private fun failure(error: Throwable): ParkingFailure {
        var cause = error
        while (cause is CompletionException && cause.cause != null) cause = requireNotNull(cause.cause)
        return cause as? ParkingFailure ?: ParkingFailure(-1)
    }
    private fun <T> await(future: CompletableFuture<T>, success: (T) -> Unit, failed: (ParkingFailure) -> Unit = { e ->
        state = state.copy(message = failureMessage(e), mustRefresh = true)
    }) {
        val ticket = epoch; state = state.copy(busy = true, message = null); tasks.add(future)
        future.whenComplete { value, error -> main.post {
            tasks.remove(future)
            if (ticket == epoch) {
                state = state.copy(busy = false)
                if (error == null) success(value) else failed(failure(error))
            }
        } }
    }
    fun catalogs() {
        val client = api ?: return
        if (state.busy || state.pending != null) return
        await(client.vehicles(token).thenCombine(client.objects(token)) { vehicles, objects -> vehicles to objects }, { (vehicles, objects) ->
            val selected = state.vehicleId?.takeIf { id -> vehicles.any { it.id == id } }
            state = state.copy(connected = true, vehicles = vehicles, objects = objects, vehicleId = selected,
                objectId = state.objectId?.takeIf { id -> objects.any { it.id == id } }, mustRefresh = true)
            if (selected != null) refreshSessions()
        }, { e ->
            // Never use local fixtures after a failed network connection.
            state = state.copy(connected = false, vehicles = emptyList(), objects = emptyList(), message = failureMessage(e))
        })
    }
    fun selectVehicle(id: String) {
        if (state.busy || state.pending != null || state.vehicles.none { it.id == id }) return
        state = state.copy(vehicleId = id, sessions = emptyList(), sessionId = null, mustRefresh = true, lastSaved = null)
        refreshSessions()
    }
    fun selectObject(id: String) {
        if (!state.busy && state.pending == null && state.objects.any { it.id == id }) state = state.copy(objectId = id)
    }
    fun selectSession(id: String) {
        if (!state.busy && state.pending == null && state.sessions.any { it.id == id }) state = state.copy(sessionId = id)
    }
    fun refreshSessions(after: String? = null) {
        val client = api ?: return; val vehicle = state.vehicleId ?: return
        if (state.busy || state.pending != null) return
        state = state.copy(mustRefresh = true)
        await(client.sessions(token, vehicle), { sessions ->
            state = state.copy(sessions = sessions, mustRefresh = false, message = after,
                sessionId = state.sessionId?.takeIf { id -> sessions.any { it.id == id } })
        })
    }
    fun create(endAt: String) {
        if (!ready()) return
        if (state.sessions.any { it.status == "active" }) {
            state = state.copy(message = "У автомобиля уже есть активная сессия. Выберите её и подтвердите время."); return
        }
        val vehicle = state.vehicleId ?: return; val obj = state.objectId ?: return
        try { submit(SessionAction.create(vehicle, obj, endAt)) }
        catch (_: Exception) { state = state.copy(message = "Укажите будущее время окончания в ISO 8601 с часовым поясом: Z или +03:00.") }
    }
    fun confirm(endAt: String) {
        if (!ready()) return
        val session = state.sessions.find { it.id == state.sessionId } ?: return
        try { submit(SessionAction.confirm(session, endAt)) }
        catch (_: Exception) { state = state.copy(message = "Проверьте будущее время окончания в ISO 8601.") }
    }
    private fun ready() = state.connected && !state.busy && state.pending == null && !state.mustRefresh
    fun retryPending() {
        if (state.busy) return
        state.pending?.let(::submit) // Same immutable path/body/idempotencyKey/expectedRevision.
    }
    private fun submit(action: SessionAction) {
        val client = api ?: return
        state = state.copy(pending = action)
        await(client.mutate(token, action), { saved ->
            state = state.copy(pending = null, lastSaved = saved, sessionId = saved.id, mustRefresh = true)
            refreshSessions("Сессия сохранена сервером. Оплата не подтверждена.")
        }, { e ->
            if (e.uncertain) {
                state = state.copy(pending = action, mustRefresh = true,
                    message = failureMessage(e) + " Результат неизвестен. Повторите тот же запрос кнопкой ниже; его ключ и тело сохранены в памяти.")
            } else {
                state = state.copy(pending = null, mustRefresh = true, message = failureMessage(e))
                if (e.status == 409) refreshSessions("Конфликт 409: состояние перечитано. Для новой попытки явно выберите сессию и подтвердите время с её актуальной ревизией.")
            }
        })
    }
    override fun onCleared() { disconnect(); super.onCleared() }
}
