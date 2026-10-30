package ru.russtech.parking.ui

import android.app.Application
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import ru.russtech.parking.data.LocalStateStore
import ru.russtech.parking.domain.DemoRepository
import ru.russtech.parking.domain.ParkingState

class ParkingViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = DemoRepository(LocalStateStore(application))
    var state by mutableStateOf(repository.state())
        private set
    var message by mutableStateOf(repository.restoreWarning)
        private set
    fun dismissMessage() { message = null }
    private fun action(work: () -> ParkingState) {
        try { state = work() }
        catch (error: Exception) { message = error.message ?: "Не удалось выполнить действие." }
    }
    fun next() = action { repository.nextPosition() }
    fun advance(minutes: Int) = action { repository.advanceMinutes(minutes) }
    fun session(minutes: Int) = action {
        if (state.activeSession == null) repository.startSession(minutes) else repository.confirmSession(minutes)
    }
    fun payment() {
        val link = repository.paymentLink()
        message = if (link.mode == "unavailable") "Официальный адрес оплаты ещё не согласован. Реальная оплата не выполняется; статус оплаты не изменён." else "Демонстрационный платёжный адаптер."
    }
    fun reset() = action { repository.reset() }
}
