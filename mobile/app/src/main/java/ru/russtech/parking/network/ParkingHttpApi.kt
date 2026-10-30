package ru.russtech.parking.network

import org.json.JSONObject
import java.io.Closeable
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URI
import java.time.Instant
import java.time.OffsetDateTime
import java.util.UUID
import java.util.concurrent.CompletableFuture
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

// Server DTOs are deliberately separate from domain.ParkingSession and DemoParkingEngine.
data class ServerVehicle(val id: String, val driverId: String, val registration: String, val displayName: String)
data class ServerObject(val id: String, val externalZoneId: String, val displayName: String)
data class ServerSession(
    val id: String, val vehicleId: String, val objectId: String, val startedAt: String,
    val endAt: String, val status: String, val revision: Long, val paymentConfirmed: Boolean
)

/** Immutable wire request: retries MUST reuse this object, including path, key and exact body. No token. */
data class SessionAction(val path: String, val body: String) {
    companion object {
        private fun future(value: String, now: Instant): String {
            val instant = OffsetDateTime.parse(value.trim()).toInstant()
            require(instant > now) { "Укажите будущее время окончания в ISO 8601." }
            return instant.toString()
        }
        fun create(vehicleId: String, objectId: String, endAt: String, now: Instant = Instant.now()): SessionAction {
            val body = JSONObject().put("objectId", uuid(objectId)).put("endAt", future(endAt, now))
                .put("idempotencyKey", UUID.randomUUID().toString()).toString()
            return SessionAction("/api/vehicles/${uuid(vehicleId)}/sessions", body)
        }
        fun confirm(session: ServerSession, endAt: String, now: Instant = Instant.now()): SessionAction {
            require(session.revision >= 1)
            val body = JSONObject().put("endAt", future(endAt, now)).put("expectedRevision", session.revision)
                .put("idempotencyKey", UUID.randomUUID().toString()).toString()
            return SessionAction("/api/sessions/${uuid(session.id)}/confirm", body)
        }
    }
}

fun uuid(value: String): String {
    require(Regex("[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}").matches(value))
    return UUID.fromString(value).toString()
}

class ParkingFailure(val status: Int) : RuntimeException("Parking operation failed") {
    val uncertain: Boolean get() = status == 0 || status == -1 || status >= 500
}
fun failureMessage(error: ParkingFailure): String = when (error.status) {
    401 -> "Токен недействителен. Отключитесь и введите действующий водительский токен."
    403 -> "Нет доступа (403). Используйте свой автомобиль и водительский токен."
    400, 422 -> "Сервер отклонил данные. Проверьте объект и будущее время окончания."
    404 -> "Автомобиль, объект или сессия не найдены. Обновите данные."
    409 -> "Конфликт состояния или ревизии (409). Перед новым действием нужно перечитать сессии."
    0 -> "Нет связи с API. Проверьте SSH-туннель, adb reverse или адрес эмулятора."
    -1 -> "Неожиданный формат ответа API. Исход операции может быть неизвестен."
    else -> "Сервис временно недоступен. Исход операции может быть неизвестен."
}

data class WireReply(val status: Int, val body: String)
fun interface HttpTransport {
    fun execute(origin: URI, path: String, method: String, token: String, body: String?): WireReply
}
interface ParkingApi : Closeable {
    fun vehicles(token: String): CompletableFuture<List<ServerVehicle>>
    fun objects(token: String): CompletableFuture<List<ServerObject>>
    fun sessions(token: String, vehicleId: String): CompletableFuture<List<ServerSession>>
    fun mutate(token: String, action: SessionAction): CompletableFuture<ServerSession>
}
class UrlConnectionTransport : HttpTransport {
    override fun execute(origin: URI, path: String, method: String, token: String, body: String?): WireReply {
        val connection = origin.resolve(path).toURL().openConnection() as HttpURLConnection
        try {
            connection.instanceFollowRedirects = false // Never forward bearer credentials to redirects.
            connection.connectTimeout = 12_000; connection.readTimeout = 15_000
            connection.requestMethod = method
            connection.setRequestProperty("Accept", "application/json")
            connection.setRequestProperty("Authorization", "Bearer $token")
            if (body != null) {
                connection.doOutput = true
                connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            }
            val status = connection.responseCode
            if (status !in 200..299) return WireReply(status, "") // Raw errors are neither rendered nor logged.
            val bytes = connection.inputStream.use { it.readBytesLimited(8_000_000) }
            return WireReply(status, bytes.toString(Charsets.UTF_8))
        } finally { connection.disconnect() }
    }
    private fun java.io.InputStream.readBytesLimited(limit: Int): ByteArray {
        val buffer = java.io.ByteArrayOutputStream(); val chunk = ByteArray(8192)
        while (true) {
            val n = read(chunk); if (n < 0) return buffer.toByteArray()
            if (buffer.size() + n > limit) throw ParkingFailure(-1)
            buffer.write(chunk, 0, n)
        }
    }
}

/** All I/O and JSON conversion run off the UI thread. No retry and no demo fallback. */
class ParkingHttpApi(
    endpoint: String,
    allowDebugLocalHttp: Boolean,
    private val transport: HttpTransport = UrlConnectionTransport(),
    private val executor: ExecutorService = Executors.newFixedThreadPool(2) { work -> Thread(work, "parking-http").apply { isDaemon = true } }
) : ParkingApi {
    private val origin = origin(endpoint, allowDebugLocalHttp)
    companion object {
        fun origin(value: String, debug: Boolean): URI {
            val uri = URI(value.trim())
            require(uri.host != null && uri.rawUserInfo == null && uri.rawQuery == null && uri.rawFragment == null && uri.path in listOf("", "/"))
            require(uri.scheme == "https" || (debug && uri.scheme == "http" && uri.host in listOf("127.0.0.1", "10.0.2.2"))) {
                "HTTP разрешён только для локального debug-подключения."
            }
            require(uri.port == -1 || uri.port in 1..65535)
            return URI(uri.scheme, null, uri.host, uri.port, "/", null, null)
        }
    }
    private fun <T> async(work: () -> T): CompletableFuture<T> = CompletableFuture.supplyAsync({
        try { work() }
        catch (e: ParkingFailure) { throw e }
        catch (_: IOException) { throw ParkingFailure(0) }
        catch (_: Exception) { throw ParkingFailure(-1) }
    }, executor)
    private fun json(path: String, token: String, body: String? = null): JSONObject {
        require(token.isNotBlank() && token.none { it.isWhitespace() })
        val reply = transport.execute(origin, path, if (body == null) "GET" else "POST", token, body)
        val expected = if (body == null || path.endsWith("/confirm")) 200 else 201
        if (reply.status != expected) throw ParkingFailure(if (reply.status in 200..399) -1 else reply.status)
        return JSONObject(reply.body)
    }
    private fun <T> pages(path: String, token: String, map: (JSONObject) -> T): List<T> {
        val result = mutableListOf<T>(); var current = 1
        while (true) {
            val reply = json(path + (if ('?' in path) "&" else "?") + "page=$current&pageSize=50", token)
            require(reply.getInt("page") == current && reply.getInt("pageSize") == 50)
            val total = reply.getLong("total"); require(total in 0..10_000)
            val items = reply.getJSONArray("items"); require(items.length() <= 50)
            for (i in 0 until items.length()) result.add(map(items.getJSONObject(i)))
            if (result.size.toLong() == total) return result
            require(items.length() > 0 && result.size.toLong() < total)
            current++
        }
    }
    override fun vehicles(token: String) = async { pages("/api/vehicles", token) { x ->
        ServerVehicle(uuid(x.getString("id")), uuid(x.getString("driverId")), x.getString("registration"), x.getString("displayName"))
    } }
    override fun objects(token: String) = async { pages("/api/parking-objects?city=spb", token) { x ->
        ServerObject(uuid(x.getString("id")), x.getString("externalZoneId"), x.getString("displayName"))
    } }
    override fun sessions(token: String, vehicleId: String) = async { pages("/api/vehicles/${uuid(vehicleId)}/sessions", token, ::session) }
    override fun mutate(token: String, action: SessionAction) = async {
        require(Regex("/api/vehicles/[0-9a-f-]{36}/sessions|/api/sessions/[0-9a-f-]{36}/confirm").matches(action.path))
        session(json(action.path, token, action.body))
    }
    private fun session(x: JSONObject): ServerSession {
        val started = x.getString("startedAt"); val end = x.getString("endAt")
        OffsetDateTime.parse(started); OffsetDateTime.parse(end)
        val status = x.getString("status"); require(status in listOf("active", "expired"))
        val revision = x.getLong("revision"); require(revision >= 1)
        val paid = x.getBoolean("paymentConfirmed"); require(!paid)
        return ServerSession(uuid(x.getString("id")), uuid(x.getString("vehicleId")), uuid(x.getString("objectId")), started, end, status, revision, paid)
    }
    override fun close() { executor.shutdownNow() }
}
