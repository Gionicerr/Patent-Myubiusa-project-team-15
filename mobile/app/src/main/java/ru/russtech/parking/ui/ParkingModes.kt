package ru.russtech.parking.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel

private enum class ParkingMode { NETWORK, OFFLINE }

@Composable
fun ParkingModesApp() {
    var mode by remember { mutableStateOf<ParkingMode?>(null) }
    MaterialTheme {
        Surface(Modifier.fillMaxSize()) {
            Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding()) {
                if (mode != null) TextButton(onClick = { mode = null }) { Text("К выбору режима") }
                when (mode) {
                    null -> Column(Modifier.padding(24.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
                        Text("Парковка", style = MaterialTheme.typography.headlineMedium)
                        Text("Выберите источник данных. Ошибка сети не переключает приложение в демонстрацию.")
                        Button(onClick = { mode = ParkingMode.NETWORK }) { Text("Подключить парковочный API") }
                        OutlinedButton(onClick = { mode = ParkingMode.OFFLINE }) { Text("Автономное демо") }
                        Text("API: проверенные сервером автомобили и сессии. Демо: синтетические координаты, локальное состояние и управляемое время.")
                    }
                    ParkingMode.NETWORK -> {
                        val network: NetworkParkingViewModel = viewModel()
                        DisposableEffect(network) { onDispose { network.disconnect() } }
                        Box(Modifier.weight(1f)) { NetworkParkingScreen(network) }
                    }
                    ParkingMode.OFFLINE -> Box(Modifier.weight(1f)) { ParkingApp(viewModel<ParkingViewModel>()) }
                }
            }
        }
    }
}
