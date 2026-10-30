package ru.russtech.parking.data

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import ru.russtech.parking.domain.*

class LocalStateStore(context: Context) : StateStore {
    private val preferences = context.getSharedPreferences("parking_demo", Context.MODE_PRIVATE)
    override fun load(): ParkingState? = preferences.getString("snapshot", null)?.let(SnapshotCodec::decode)
    override fun save(state: ParkingState) {
        check(preferences.edit().putString("snapshot", SnapshotCodec.encode(state)).commit()) {
            "Не удалось сохранить данные на устройстве. Действие не применено."
        }
    }
}
object SnapshotCodec {
    fun encode(state: ParkingState): String = JSONObject().apply {
        put("version", 1); put("now", state.now); put("pointIndex", state.pointIndex)
        put("stableObjectId", state.stableObjectId ?: JSONObject.NULL)
        put("sessions", JSONArray().apply { state.sessions.forEach { s -> put(JSONObject().apply {
            put("id", s.id); put("objectId", s.objectId); put("startedAt", s.startedAt); put("endAt", s.endAt)
            put("revision", s.revision); put("expired", s.expired); put("warned", s.warned); put("paymentConfirmed", s.paymentConfirmed)
        }) } })
        put("events", JSONArray().apply { state.events.forEach { e -> put(JSONObject().apply {
            put("id", e.id); put("type", e.type); put("occurredAt", e.occurredAt); put("message", e.message)
            put("sessionId", e.sessionId ?: JSONObject.NULL)
        }) } })
    }.toString()
    fun decode(raw: String): ParkingState {
        val json = JSONObject(raw)
        require(json.getInt("version") == 1) { "Unsupported snapshot version" }
        val now = json.getLong("now"); require(now > 0)
        val pointIndex = json.getInt("pointIndex"); require(pointIndex in DemoRoute.points.indices)
        val stableId = if (json.isNull("stableObjectId")) null else json.getString("stableObjectId")
        require(stableId == null || DemoRoute.objectById(stableId) != null)
        val sessionsJson = json.getJSONArray("sessions"); require(sessionsJson.length() <= 100)
        val sessions = (0 until sessionsJson.length()).map { index ->
            val s = sessionsJson.getJSONObject(index)
            ParkingSession(s.getString("id"), s.getString("objectId"), s.getLong("startedAt"), s.getLong("endAt"),
                s.getInt("revision"), s.getBoolean("expired"), s.getBoolean("warned"), s.getBoolean("paymentConfirmed")).also {
                require(it.id.isNotBlank() && DemoRoute.objectById(it.objectId) != null)
                require(it.startedAt > 0 && it.endAt > it.startedAt && it.revision > 0 && !it.paymentConfirmed)
                require(it.expired || it.endAt > now)
            }
        }
        require(sessions.count { !it.expired } <= 1)
        require(sessions.map { it.id }.distinct().size == sessions.size)
        val eventJson = json.getJSONArray("events"); require(eventJson.length() <= 500)
        val events = (0 until eventJson.length()).map { index ->
            val e = eventJson.getJSONObject(index)
            ParkingEvent(e.getString("id"), e.getString("type"), e.getLong("occurredAt"), e.getString("message"),
                if (e.isNull("sessionId")) null else e.getString("sessionId")).also {
                require(it.id.isNotBlank() && it.occurredAt in 1..now && it.message.isNotBlank())
            }
        }
        return ParkingState(now, pointIndex, stableId, sessions, events)
    }
}
