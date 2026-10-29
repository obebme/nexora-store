import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.route('**/api/payments/config', async (route) => {
    await route.fulfill({
      json: { configured: true, sales_enabled: true, checkout_available: true },
    })
  })
  await page.route('**/api/products?limit=100', async (route) => {
    await route.fulfill({ json: [] })
  })
})

test('registration guides a new customer to email verification', async ({ page }) => {
  await page.route('**/api/auth/register', async (route) => {
    await route.fulfill({
      status: 201,
      json: { message: 'Подтверди email по ссылке из письма.' },
    })
  })

  await page.goto('/')
  await page.getByRole('button', { name: 'АККАУНТ' }).click()
  await page.getByRole('button', { name: 'СОЗДАТЬ АККАУНТ' }).click()
  await page.getByLabel('EMAIL').fill('buyer@example.com')
  await page.getByLabel('ПАРОЛЬ').fill('strong-test-password')
  await page.getByRole('button', { name: /СОЗДАТЬ АККАУНТ/, exact: false }).last().click()

  await expect(page.getByRole('heading', { name: /ПРОВЕРЬ ПОЧТУ/ })).toBeVisible()
  await expect(page.getByText('buyer@example.com')).toBeVisible()
})

test('email verification shows its confirmed state', async ({ page }) => {
  await page.route('**/api/auth/verify-email?token=test-token', async (route) => {
    await route.fulfill({
      json: {
        email: 'buyer@example.com',
        verified: true,
        notification_sent: true,
        message: 'Адрес электронной почты подтверждён.',
      },
    })
  })

  await page.goto('/email/verified?token=test-token')

  await expect(page.getByRole('heading', { name: /ПОЧТА.*ПОДТВЕРЖДЕНА/ })).toBeVisible()
  await expect(page.getByText('Письмо с результатом отправлено на ваш адрес.')).toBeVisible()
})

test('customer can add an item and start a payment accessibly', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('nexora-token', 'test-token'))
  await page.route('**/api/cart', async (route) => {
    if (route.request().method() === 'PUT') {
      await route.fulfill({
        json: {
          items: [
            {
              product_id: 1,
              selected_size: '39',
              quantity: 1,
              unit_price: '12990.00',
            },
          ],
        },
      })
      return
    }
    await route.continue()
  })
  await page.route('**/api/orders', async (route) => {
    await route.fulfill({ status: 201, json: { id: 42 } })
  })
  await page.route('**/api/orders/42/payment', async (route) => {
    await route.fulfill({
      json: {
        confirmation_url: 'http://127.0.0.1:4173/payment/return?order_id=42',
      },
    })
  })

  await page.goto('/')
  await page.getByRole('button', { name: 'Подробнее о товаре RIFT RUNNER 02' }).click()
  await page.getByRole('button', { name: 'Размер 39' }).click()
  await page.getByRole('button', { name: /ДОБАВИТЬ В СУМКУ/ }).click()
  await page.getByRole('button', { name: /ОФОРМИТЬ ЗАКАЗ/ }).click()

  const checkout = page.getByRole('dialog', { name: /ОФОРМЛЕНИЕ ЗАКАЗА/ })
  await expect(checkout).toBeVisible()
  await checkout.getByLabel('ИМЯ').fill('Test Buyer')
  await checkout.getByLabel('EMAIL').fill('buyer@example.com')
  await checkout.getByLabel('ПАРОЛЬ ДЛЯ АККАУНТА').fill('strong-test-password')
  await checkout.getByLabel('УЛИЦА И ДОМ').fill('1 Test Street')
  await checkout.getByLabel('ГОРОД').fill('Москва')
  await checkout.getByLabel('ИНДЕКС').fill('101000')
  const orderRequest = page.waitForRequest(
    (request) => request.url().endsWith('/api/orders') && request.method() === 'POST',
  )
  const paymentRequest = page.waitForRequest(
    (request) => request.url().endsWith('/api/orders/42/payment'),
  )
  await checkout.getByRole('button', { name: /ПЕРЕЙТИ К ОПЛАТЕ/ }).click()
  const order = await orderRequest
  expect(order.postDataJSON().shipping.country_code).toBe('RU')
  await paymentRequest
  await expect(page.getByRole('button', { name: /Возврат с оплаты заказа №42/ })).toBeVisible()
})
