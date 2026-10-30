import { test, expect } from '@playwright/test';
const note = { id: '6cb16042-b0b4-4b36-bca4-84ad8c11ed5f', ownerId: 'test-owner', title: 'Встреча команды', text: 'Обсудить контракт API', createdAt: '2026-10-30T12:00:00Z' };
for (const viewport of [{ width: 1440, height: 1050 }, { width: 390, height: 844 }]) {
  test(`mock create and responsive layout at ${viewport.width}px`, async ({ page }, info) => {
    await page.setViewportSize(viewport);
    const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:4200/');
    await expect(page).toHaveURL(/\/notes$/);
    await expect(page.getByText('Тестовые данные. Сервер не подключён')).toBeVisible();
    await page.getByRole('button', { name: 'Начать тестовый сеанс' }).click();
    await expect(page.getByRole('heading', { name: 'Начните с первой заметки' })).toBeVisible();
    await page.getByLabel('Заголовок', { exact: true }).fill('   ');
    await page.getByRole('button', { name: 'Создать заметку' }).click();
    await expect(page.getByText('Введите заголовок, не только пробелы')).toBeVisible();
    await page.getByLabel('Заголовок', { exact: true }).fill(note.title);
    await page.getByLabel('Текст заметки', { exact: true }).fill(note.text);
    await page.getByRole('button', { name: 'Создать заметку' }).click();
    await expect(page.getByText('Заметка создана.', { exact: true })).toBeVisible();
    await expect(page.getByRole('article')).toHaveCount(1);
    await expect(page.locator('mat-error')).toHaveCount(0);
    await expect(page.getByRole('article')).toContainText(note.title);
    await expect(page.getByRole('article')).toContainText(note.text);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: info.outputPath(`notes-${viewport.width}.png`), fullPage: true });
    await page.getByRole('button', { name: 'Завершить сеанс' }).click();
    await expect(page.getByRole('article')).toHaveCount(0);
    expect(errors).toEqual([]);
  });
}

test('HTTP mode uses the contract and never falls back to mock', async ({ page }) => {
  let created = false;
  const requests: { method: string; authorization: string | undefined; body: unknown }[] = [];
  await page.route('**/api/notes', async route => {
    const req = route.request();
    requests.push({ method: req.method(), authorization: req.headers()['authorization'], body: req.postDataJSON() });
    if (req.method() === 'POST') {
      created = true; await route.fulfill({ status: 201, json: note });
    } else { await route.fulfill({ json: created ? [note] : [] }); }
  });
  await page.goto('http://127.0.0.1:4201/notes');
  await expect(page.getByText('Тестовые данные. Сервер не подключён')).toHaveCount(0);
  await page.getByLabel('Токен приложения', { exact: true }).fill('fictitious-browser-token');
  await page.getByRole('button', { name: 'Подключиться', exact: true }).click();
  await expect(page.getByText('Начните с первой заметки')).toBeVisible();
  await page.getByLabel('Заголовок', { exact: true }).fill(note.title);
  await page.getByLabel('Текст заметки', { exact: true }).fill(note.text);
  await page.getByRole('button', { name: 'Создать заметку' }).click();
  await expect(page.getByRole('article')).toHaveCount(1);
  expect(requests.map(r => r.method)).toEqual(['GET', 'POST', 'GET']);
  expect(requests[1].body).toEqual({ title: note.title, text: note.text });
  expect(requests.every(r => r.authorization === 'Bearer fictitious-browser-token')).toBe(true);
  expect(await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length }))).toEqual({ local: 0, session: 0 });
  await expect(page.getByLabel('Токен приложения', { exact: true })).toHaveValue('');
});

test('unavailable real API remains an error, not test data', async ({ page }) => {
  await page.goto('http://127.0.0.1:4201/notes');
  await page.getByLabel('Токен приложения', { exact: true }).fill('fictitious-unavailable-token');
  await page.getByRole('button', { name: 'Подключиться', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Не удалось загрузить заметки');
  await expect(page.getByRole('article')).toHaveCount(0);
  await expect(page.getByText('Тестовые данные. Сервер не подключён')).toHaveCount(0);
});

test('401 is actionable and preserves the draft', async ({ page }) => {
  await page.route('**/api/notes', route => route.fulfill({ status: 401, json: { code: 'unauthorized', message: 'test' } }));
  await page.goto('http://127.0.0.1:4201/notes');
  await page.getByLabel('Токен приложения', { exact: true }).fill('fictitious-expired-token');
  await page.getByRole('button', { name: 'Подключиться', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Токен недействителен');
  await page.getByLabel('Заголовок', { exact: true }).fill('Черновик');
  await page.getByRole('button', { name: 'Создать заметку' }).click();
  await expect(page.getByLabel('Заголовок', { exact: true })).toHaveValue('Черновик');
  await expect(page.locator('.compose [role=alert]')).toContainText('Токен недействителен');
});
