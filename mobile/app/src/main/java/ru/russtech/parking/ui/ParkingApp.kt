package ru.russtech.parking.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ru.russtech.parking.domain.*
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlin.math.ceil

private val Ink = Color(0xFF203E37)
private val Green = Color(0xFF20594F)
private val Muted = Color(0xFF5D7166)
private val Warm = Color(0xFFFFF2D5)
private val Surface = Color(0xFFF5F7F2)
private fun time(value: Long) = DateTimeFormatter.ofPattern("HH:mm").withZone(ZoneId.systemDefault()).format(Instant.ofEpochMilli(value))
private fun fullTime(value: Long) = DateTimeFormatter.ofPattern("dd.MM, HH:mm").withZone(ZoneId.systemDefault()).format(Instant.ofEpochMilli(value))

@Composable
fun ParkingApp(model: ParkingViewModel) {
    MaterialTheme(colorScheme = lightColorScheme(primary = Green, onPrimary = Color.White,
        background = Surface, surface = Color.White, onSurface = Ink, secondaryContainer = Color(0xFFDCE9DF))) {
        var tab by rememberSaveable { mutableIntStateOf(0) }
        var editingSession by rememberSaveable { mutableStateOf(false) }
        var resetDialog by rememberSaveable { mutableStateOf(false) }
        val state = model.state
        val scrollState = rememberScrollState()
        LaunchedEffect(tab, editingSession) { scrollState.scrollTo(0) }
        Scaffold(containerColor = Surface,
            bottomBar = {
                Column(Modifier.fillMaxWidth().background(Color.White), horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("Демо · сервер не подключён", Modifier.padding(top = 8.dp), fontSize = 10.sp, color = Muted)
                    NavigationBar(containerColor = Color.White) {
                    listOf("Карта", "Сессия", "История").forEachIndexed { index, title ->
                        NavigationBarItem(selected = tab == index, onClick = { tab = index; editingSession = false },
                            icon = { Text(listOf("P", "◷", "≡")[index], fontWeight = FontWeight.Bold, fontSize = 22.sp) },
                            label = { Text(title) })
                    }
                    }
                }
            }) { padding ->
            Column(Modifier.fillMaxSize().padding(padding).verticalScroll(scrollState)
                .widthIn(max = 680.dp).padding(horizontal = 20.dp, vertical = 18.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Surface(color = Green, shape = RoundedCornerShape(12.dp)) { Text("P", Modifier.padding(horizontal = 15.dp, vertical = 9.dp), color = Color.White, fontSize = 25.sp, fontWeight = FontWeight.Bold) }
                        Column { Text("Парковка", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold); Text("Помощник водителя", color = Muted, fontSize = 11.sp) }
                    }
                    TextButton(onClick = { resetDialog = true }) { Text("Сбросить") }
                }
                Notice("ДЕМОНСТРАЦИОННЫЙ РЕЖИМ", "Сервер не подключён. Маршрут, объекты и время тестовые. Реальная оплата не выполняется.", Warm)
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text("Автомобиль · ДЕМО-01", color = Muted, fontSize = 12.sp)
                    Text("Демо-время ${time(state.now)}", color = Green, fontSize = 12.sp, fontWeight = FontWeight.Medium)
                }
                if (editingSession) SessionEditor(state.activeSession != null, onDismiss = { editingSession = false }) { minutes ->
                    model.session(minutes); editingSession = false
                } else when (tab) {
                    0 -> MapScreen(state, model::next, { editingSession = true }, model::advance)
                    1 -> SessionScreen(state, { editingSession = true }, model::payment, model::advance)
                    2 -> HistoryScreen(state)
                }
                Text("Время — местное. Демо-часы изменяются только кнопками. Состояние сохраняется на устройстве.", color = Muted, fontSize = 11.sp)
                Spacer(Modifier.height(8.dp))
            }
        }
        if (model.message != null) AlertDialog(onDismissRequest = model::dismissMessage,
            title = { Text("Информация") }, text = { Text(model.message.orEmpty()) },
            confirmButton = { TextButton(onClick = model::dismissMessage) { Text("Понятно") } })
        if (resetDialog) AlertDialog(onDismissRequest = { resetDialog = false }, title = { Text("Начать демонстрацию заново?") },
            text = { Text("Текущая сессия, маршрут и локальная история будут удалены. На сервер это не влияет.") },
            confirmButton = { TextButton(onClick = { model.reset(); resetDialog = false }) { Text("Сбросить данные") } },
            dismissButton = { TextButton(onClick = { resetDialog = false }) { Text("Отмена") } })
    }
}

@Composable
private fun Notice(title: String, body: String, color: Color = Color(0xFFEAF0E5)) {
    Surface(color = color, shape = RoundedCornerShape(12.dp)) {
        Column(Modifier.fillMaxWidth().padding(15.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
            Text(title, fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp, color = Ink)
            Text(body, fontSize = 12.sp, lineHeight = 18.sp, color = Ink)
        }
    }
}
@Composable
private fun Section(title: String, content: @Composable ColumnScope.() -> Unit) {
    Card(colors = CardDefaults.cardColors(containerColor = Color.White), shape = RoundedCornerShape(18.dp)) {
        Column(Modifier.fillMaxWidth().padding(20.dp), verticalArrangement = Arrangement.spacedBy(13.dp)) {
            Text(title, fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
            content()
        }
    }
}
@Composable
private fun MapScreen(state: ParkingState, next: () -> Unit, session: () -> Unit, advance: (Int) -> Unit) {
    Text("Ваш маршрут", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Medium)
    Surface(shape = RoundedCornerShape(18.dp), color = Color(0xFFE9EDE4)) {
        Column {
            RouteMap(state)
            Text("Схема, не географическая карта. Области условные и не являются границами тарифных зон.", Modifier.padding(14.dp), color = Muted, fontSize = 11.sp, lineHeight = 16.sp)
        }
    }
    val point = state.point
    Section(if (point.state == MatchState.MATCHED) "Объект определён" else "Зона не определена") {
        if (point.state == MatchState.MATCHED) {
            Text(DemoRoute.objectById(point.objectId)?.label.orEmpty(), fontSize = 24.sp, color = Green)
            Text("Идентификатор демо-объекта: ${point.objectId}", color = Muted, fontSize = 12.sp)
            Text("Номер тарифной зоны и стоимость не подтверждены. Не используйте эти данные для реальной оплаты.", fontSize = 12.sp, color = Muted)
        } else {
            Text(when (point.state) {
                MatchState.NO_MATCH -> "Подходящий объект не найден. Это не означает, что парковка бесплатная."
                MatchState.NO_COORDINATES -> "Координаты не получены. Это отличается от отсутствия платной зоны."
                MatchState.TECHNICAL_ERROR -> "Техническая ошибка определения местоположения."
                MatchState.AMBIGUOUS -> "Несколько возможных совпадений. Переключение объекта не подтверждено."
                MatchState.STALE -> "Наблюдение устарело. Оно не подтверждает смену зоны."
                else -> ""
            }, color = Muted, fontSize = 13.sp)
        }
        if (point.latitude != null && point.longitude != null) Text("${"%.5f".format(point.latitude)}, ${"%.5f".format(point.longitude)} · тестовая позиция", fontSize = 11.sp, color = Muted)
        if (state.activeSession == null) {
            Button(onClick = session, enabled = point.state == MatchState.MATCHED, modifier = Modifier.fillMaxWidth()) { Text("Запустить сессию") }
        } else {
            val s = requireNotNull(state.activeSession)
            Text("Сессия ${DemoRoute.objectById(s.objectId)?.label} до ${time(s.endAt)} сохраняется.", color = Green, fontSize = 13.sp)
            if (point.objectId != s.objectId) Notice("ПРОВЕРЬТЕ НЕОБХОДИМОСТЬ ОПЛАТЫ", "Текущее положение отличается от объекта сессии. Автоматическая новая оплата не выполняется.", Warm)
        }
    }
    Section("Демонстрационный маршрут") {
        Text("Точка ${state.pointIndex + 1} из ${DemoRoute.points.size} · ${state.point.caption}", color = Muted, fontSize = 13.sp)
        Button(onClick = next, enabled = state.pointIndex < DemoRoute.points.lastIndex, modifier = Modifier.fillMaxWidth()) { Text("Следующая точка маршрута") }
        Text("Последовательность включает въезд, смену объекта, выезд, потерю координат и ошибку.", fontSize = 11.sp, color = Muted)
    }
    ClockControls(advance)
    RecentEvents(state)
}

@Composable
private fun RouteMap(state: ParkingState) {
    Canvas(Modifier.fillMaxWidth().height(250.dp).semantics { contentDescription = "Схема тестового маршрута; текущая точка ${state.pointIndex + 1}. Условные объекты А и Б." }) {
        fun position(lat: Double, lon: Double) = Offset(((lon - 30.327) / .012 * size.width).toFloat(), ((59.939 - lat) / .008 * size.height).toFloat())
        // Decorative street grid, not a claim of actual road geometry.
        for (i in 1..5) {
            drawLine(Color.White, Offset(size.width * i / 6, 0f), Offset(size.width * i / 6, size.height), 13.dp.toPx())
            drawLine(Color.White, Offset(0f, size.height * i / 6), Offset(size.width, size.height * i / 6), 11.dp.toPx())
        }
        DemoRoute.objects.forEach { obj ->
            val c = position(obj.latitude, obj.longitude)
            val w = size.width * .25f; val h = size.height * .30f
            drawRoundRect(Color(0x553F8F74), Offset(c.x - w/2, c.y - h/2), Size(w, h), CornerRadius(10.dp.toPx()))
            drawRoundRect(Color(0xFF7BA58A), Offset(c.x - w/2, c.y - h/2), Size(w, h), CornerRadius(10.dp.toPx()), style = Stroke(1.5.dp.toPx()))
        }
        val points = DemoRoute.points.take(state.pointIndex + 1).filter { it.latitude != null && it.longitude != null }
        if (points.size > 1) {
            val path = Path()
            points.forEachIndexed { i, p -> val c = position(requireNotNull(p.latitude), requireNotNull(p.longitude)); if (i == 0) path.moveTo(c.x, c.y) else path.lineTo(c.x, c.y) }
            drawPath(path, Green, style = Stroke(4.dp.toPx(), cap = StrokeCap.Round))
        }
        val point = state.point
        if (point.latitude != null && point.longitude != null) {
            val c = position(point.latitude, point.longitude)
            drawCircle(Color.White, 12.dp.toPx(), c)
            drawCircle(if (point.state == MatchState.STALE) Color.Gray else Green, 7.dp.toPx(), c)
        }
    }
}
@Composable
private fun SessionScreen(state: ParkingState, session: () -> Unit, payment: () -> Unit, advance: (Int) -> Unit) {
    Text("Парковочная сессия", style = MaterialTheme.typography.headlineMedium)
    val active = state.activeSession
    if (active == null) {
        Section("Нет активной сессии") {
            Text("Найдите объект на вкладке «Карта» и явно запустите сессию. Движение по маршруту само по себе её не создаёт.", color = Muted, fontSize = 13.sp)
            Button(onClick = session, enabled = state.point.state == MatchState.MATCHED, modifier = Modifier.fillMaxWidth()) { Text("Запустить сессию") }
        }
    } else {
        Section(DemoRoute.objectById(active.objectId)?.label ?: "Объект сессии") {
            Text("ДО ОКОНЧАНИЯ", fontSize = 10.sp, letterSpacing = 1.sp, color = Muted)
            Text("${ceil((active.endAt - state.now) / 60_000.0).toInt()} мин", fontSize = 44.sp, color = Green)
            Text("Окончание: ${fullTime(active.endAt)} · местное время", fontSize = 12.sp, color = Muted)
            if (active.warned) Notice("СКОРО ОКОНЧАНИЕ", "До окончания сессии осталось не более 10 минут. Проверьте необходимость оплаты.", Warm)
            HorizontalDivider(color = Surface)
            Text("Начало: ${fullTime(active.startedAt)}\nРевизия: ${active.revision}", color = Muted, fontSize = 12.sp, lineHeight = 21.sp)
            Notice("ОПЛАТА НЕ ПОДТВЕРЖДЕНА", "Запуск и подтверждение времени сессии не подтверждают оплату.", Warm)
            Button(onClick = session, modifier = Modifier.fillMaxWidth()) { Text("Подтвердить время окончания") }
            OutlinedButton(onClick = payment, modifier = Modifier.fillMaxWidth()) { Text("Проверить переход к оплате") }
        }
    }
    ClockControls(advance)
    RecentEvents(state)
}
@Composable
private fun ClockControls(advance: (Int) -> Unit) {
    Section("Проверка времени") {
        Text("Управляемые демо-часы. Системное время телефона не изменяется.", fontSize = 12.sp, color = Muted)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            OutlinedButton(onClick = { advance(1) }, modifier = Modifier.weight(1f)) { Text("+1 мин") }
            OutlinedButton(onClick = { advance(10) }, modifier = Modifier.weight(1f)) { Text("+10 мин") }
        }
    }
}
@Composable
private fun RecentEvents(state: ParkingState) {
    state.events.lastOrNull()?.let { event -> Notice("ПОСЛЕДНЕЕ СОБЫТИЕ · ${time(event.occurredAt)}", event.message,
        if (event.type in listOf("warning_10_minutes", "session_expired", "location_error", "object_changed")) Warm else Color(0xFFE8F0E5)) }
}
@Composable
private fun HistoryScreen(state: ParkingState) {
    Text("История поездки", style = MaterialTheme.typography.headlineMedium)
    Section("Парковочные сессии · ${state.sessions.size}") {
        if (state.sessions.isEmpty()) Text("Пока нет сессий. Запустите первую после определения объекта.", color = Muted, fontSize = 13.sp)
        state.sessions.asReversed().forEach { session ->
            Text(DemoRoute.objectById(session.objectId)?.label.orEmpty(), fontWeight = FontWeight.Medium)
            Text("${fullTime(session.startedAt)} → ${fullTime(session.endAt)}\n${if (session.expired) "Время истекло" else "Активна"} · оплата не подтверждена", fontSize = 12.sp, lineHeight = 19.sp, color = Muted)
            HorizontalDivider(color = Surface)
        }
    }
    Section("Маршрут · ${state.pointIndex + 1} точек") {
        DemoRoute.points.take(state.pointIndex + 1).forEachIndexed { index, point ->
            Text("${index + 1}. ${point.caption}", fontSize = 12.sp, color = Muted)
        }
    }
    Section("События · ${state.events.size}") {
        if (state.events.isEmpty()) Text("События появятся при движении и действиях с сессией.", color = Muted, fontSize = 13.sp)
        state.events.asReversed().forEach { event ->
            Text(fullTime(event.occurredAt), fontSize = 10.sp, color = Muted)
            Text(event.message, fontSize = 13.sp, lineHeight = 20.sp)
            HorizontalDivider(color = Surface)
        }
    }
}
@Composable
private fun SessionEditor(confirm: Boolean, onDismiss: () -> Unit, onSave: (Int) -> Unit) {
    var input by rememberSaveable { mutableStateOf("30") }
    val minutes = input.toIntOrNull()
    val valid = minutes != null && minutes in 1..1440
    Section(if (confirm) "Подтвердить время" else "Запустить сессию") {
        Text("Время окончания: через указанное число минут от демо-часов. Оплата этим действием не подтверждается.", fontSize = 13.sp, color = Muted)
        OutlinedTextField(value = input, onValueChange = { input = it }, label = { Text("Минут от демо-времени") },
            modifier = Modifier.fillMaxWidth(), singleLine = true, isError = !valid,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            supportingText = { Text("От 1 до 1440 минут") })
        Button(onClick = { minutes?.let(onSave) }, enabled = valid, modifier = Modifier.fillMaxWidth()) {
            Text(if (confirm) "Подтвердить" else "Запустить")
        }
        TextButton(onClick = onDismiss, modifier = Modifier.fillMaxWidth()) { Text("Отмена") }
    }
}
