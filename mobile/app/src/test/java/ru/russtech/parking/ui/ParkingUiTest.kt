package ru.russtech.parking.ui

import android.graphics.Bitmap
import android.graphics.Canvas as AndroidCanvas
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import ru.russtech.parking.MainActivity
import java.io.File

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35], qualifiers = "w411dp-h891dp-port-xxhdpi")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class ParkingUiTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    @Before fun reset() {
        compose.runOnIdle { ViewModelProvider(compose.activity)[ParkingViewModel::class.java].reset() }
    }
    // PixelCopy redraw callbacks are not driven by Robolectric. Use its native Canvas renderer.
    private fun screenshot(name: String) = compose.runOnIdle {
        val view = compose.activity.window.decorView
        check(view.width > 0 && view.height > 0)
        val image = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
        view.draw(AndroidCanvas(image))
        val file = File("build/reports/screenshots/$name")
        requireNotNull(file.parentFile).mkdirs()
        file.outputStream().use { check(image.compress(Bitmap.CompressFormat.PNG, 100, it)) }
        image.recycle()
    }
    private fun click(text: String) = compose.onNodeWithText(text).performScrollTo().performClick()
    @Test fun `driver can start a session and receive the ten minute warning`() {
        compose.onNodeWithText("ДЕМОНСТРАЦИОННЫЙ РЕЖИМ").assertIsDisplayed()
        click("Следующая точка маршрута")
        click("Запустить сессию")
        compose.onNodeWithText("Запустить").performClick()
        compose.onNodeWithText("Сессия", useUnmergedTree = true).performClick()
        compose.onNodeWithText("30 мин").assertExists()
        click("+10 мин"); click("+10 мин")
        compose.onNodeWithText("10 мин").assertExists()
        compose.onNodeWithText("СКОРО ОКОНЧАНИЕ").assertExists()
        compose.onNodeWithText("ОПЛАТА НЕ ПОДТВЕРЖДЕНА").assertExists()
        compose.onNodeWithText("Парковочная сессия").performScrollTo()
        screenshot("parking-session.png")
    }
    @Test fun `duration validation and reset require explicit user actions`() {
        click("Следующая точка маршрута"); click("Запустить сессию")
        compose.onNodeWithText("Минут от демо-времени").performTextReplacement("0")
        compose.onNodeWithText("Запустить").assertIsNotEnabled()
        compose.onNodeWithText("Отмена").performClick()
        compose.onNodeWithText("Ваш маршрут").performScrollTo()
        compose.onNodeWithText("Сбросить").performScrollTo().performClick()
        compose.onNodeWithText("Отмена").performClick()
        compose.onNodeWithText("Объект определён").assertExists()
        compose.onNodeWithText("Сбросить").performScrollTo().performClick()
        compose.onNodeWithText("Сбросить данные").performClick()
        compose.onNodeWithText("Зона не определена").assertExists()
        screenshot("parking-map.png")
    }
}
