package ru.russtech.parking.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import java.time.Instant

@Composable
fun NetworkParkingScreen(model: NetworkParkingViewModel) {
    val state = model.state
    var endpoint by remember { mutableStateOf("http://127.0.0.1:18881") }
    var tokenInput by remember { mutableStateOf("") } // Deliberately NOT rememberSaveable.
    var endAt by remember { mutableStateOf(Instant.now().plusSeconds(3600).toString()) }
    val editable = !state.busy && state.pending == null
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("Парковочный API", style = MaterialTheme.typography.headlineSmall)
        Text("Сетевой режим · данные с сервера · демонстрационная идентификация")
        Text("Геосопоставление, предупреждения, оплата и перемотка времени пока недоступны. Локальные демо-события здесь не вычисляются.", style = MaterialTheme.typography.bodySmall)
        if (!state.connected) {
            OutlinedTextField(endpoint, { endpoint = it }, Modifier.fillMaxWidth(), enabled = !state.busy,
                label = { Text("Адрес API") }, singleLine = true)
            Text("127.0.0.1 телефона требует adb reverse tcp:18881 tcp:18881. Для Android Emulator используйте http://10.0.2.2:18881.", style = MaterialTheme.typography.bodySmall)
            OutlinedTextField(tokenInput, { tokenInput = it }, Modifier.fillMaxWidth(), enabled = !state.busy,
                label = { Text("Водительский токен") }, singleLine = true,
                visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password))
            Button(onClick = { val token = tokenInput; tokenInput = ""; model.connect(endpoint, token) }, enabled = !state.busy && tokenInput.isNotBlank()) { Text("Подключиться к API") }
        } else {
            Text("Подключено. Токен хранится только в памяти; права проверяет сервер.")
            OutlinedButton(onClick = model::catalogs, enabled = editable) { Text("Обновить автомобили и объекты") }
        }
        if (state.connected || state.busy || state.pending != null) {
            TextButton(onClick = { tokenInput = ""; model.disconnect() }) { Text("Отключиться и очистить сетевой сеанс") }
        }
        if (state.busy) { LinearProgressIndicator(Modifier.fillMaxWidth()); Text("Запрос к серверу…") }
        state.message?.let { Text(it, color = MaterialTheme.colorScheme.primary) }
        if (state.pending != null) {
            Text("Не создавайте новое действие. Повтор отправит исходное тело и тот же idempotencyKey. При выходе из режима ключ теряется; после подключения сначала перечитайте серверное состояние.")
            Button(onClick = model::retryPending, enabled = !state.busy) { Text("Повторить тот же запрос") }
        }
        if (state.connected) {
            HorizontalDivider()
            Text("1. Выберите свой автомобиль", style = MaterialTheme.typography.titleMedium)
            Text("Для первой демонстрации предназначены свободные DEMO-CLIENT-A/B. UUID получаются из API.", style = MaterialTheme.typography.bodySmall)
            if (state.vehicles.isEmpty()) Text("Сервер не вернул автомобилей.")
            state.vehicles.forEach { vehicle ->
                OutlinedButton(onClick = { model.selectVehicle(vehicle.id) }, enabled = editable, modifier = Modifier.fillMaxWidth()) {
                    Text((if (vehicle.id == state.vehicleId) "✓ " else "") + vehicle.registration + " · " + vehicle.displayName)
                }
            }
            Text("2. Выберите объект источника", style = MaterialTheme.typography.titleMedium)
            if (state.objects.isEmpty()) Text("Сервер не вернул объектов.")
            state.objects.forEach { obj ->
                OutlinedButton(onClick = { model.selectObject(obj.id) }, enabled = editable, modifier = Modifier.fillMaxWidth()) {
                    Text((if (obj.id == state.objectId) "✓ " else "") + obj.externalZoneId + " · " + obj.displayName)
                }
            }
            OutlinedTextField(endAt, { endAt = it }, Modifier.fillMaxWidth(), enabled = editable,
                label = { Text("Будущее окончание · ISO 8601 UTC") }, singleLine = true)
            Text("Время задаётся явно, сервер проверяет его относительно своего времени. Локальные миллисекунды демо не отправляются.", style = MaterialTheme.typography.bodySmall)
            Button(onClick = { model.create(endAt) },
                enabled = editable && !state.mustRefresh && state.vehicleId != null && state.objectId != null && state.sessions.none { it.status == "active" }) {
                Text("Создать сессию на сервере")
            }
            if (state.vehicleId != null) {
                Text("3. Сессии выбранного автомобиля", style = MaterialTheme.typography.titleMedium)
                OutlinedButton(onClick = { model.refreshSessions() }, enabled = editable) { Text("Перечитать сессии с сервера") }
                if (state.mustRefresh) Text("Перед новым действием требуется успешное чтение сессий.")
                if (!state.mustRefresh && state.sessions.isEmpty()) Text("Сессий нет. Можно явно создать новую.")
                if (state.sessions.any { it.status == "active" }) Text("Уже есть активная сессия: выберите её для подтверждения. Вторая активная сессия не создаётся.")
                state.sessions.forEach { session ->
                    Card(Modifier.fillMaxWidth()) {
                        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text("id: ${session.id}")
                            Text("Объект: " + (state.objects.find { it.id == session.objectId }?.displayName ?: session.objectId))
                            Text("startedAt: ${session.startedAt}")
                            Text("endAt: ${session.endAt}")
                            Text("status: ${session.status} · revision: ${session.revision}")
                            Text("paymentConfirmed: ${session.paymentConfirmed} · это не подтверждение оплаты")
                            OutlinedButton(onClick = { model.selectSession(session.id) }, enabled = editable && !state.mustRefresh) {
                                Text(if (state.sessionId == session.id) "Сессия выбрана" else "Выбрать для подтверждения")
                            }
                        }
                    }
                }
                Button(onClick = { model.confirm(endAt) }, enabled = editable && !state.mustRefresh && state.sessionId != null) {
                    Text("Подтвердить новое время на сервере")
                }
                Text("Подтверждение использует актуальную revision выбранной сессии; её объект не меняется. Выбор объекта выше применяется только при создании.", style = MaterialTheme.typography.bodySmall)
                state.lastSaved?.let { saved ->
                    Text("Последний ответ сохранения: id=${saved.id} · revision=${saved.revision} · endAt=${saved.endAt}")
                }
            }
        }
    }
}
