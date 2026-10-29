import { useEffect, useMemo, useRef, useState } from 'react'
import './style.css'
import './product-detail.css'
import './search.css'
import './storefront-finishing.css'

type Product = { id: number; slug: string; sku?: string; description?: string; stockQuantity?: number; stockBySize?: Record<string, number>; images?: string[]; name: string; category: 'Обувь' | 'Одежда' | 'Аксессуары'; price: number; oldPrice?: number; tag?: string; image: string; color: string; sizes: string[] }
type CartLine = { product: Product; size: string; quantity: number }

const demoProducts: Product[] = [
  { id: 1, slug: 'rift-runner-02', sku: 'NX-SHO-001', description: 'Городские кроссовки с выразительным силуэтом и контрастными деталями. Созданы для повседневных маршрутов.', name: 'RIFT RUNNER 02', category: 'Обувь', price: 12990, oldPrice: 15990, tag: 'ХИТ', image: '/images/rift-runner.jpg', color: 'Молочный / графит', sizes: ['39', '40', '41', '42', '43', '44'] },
  { id: 2, slug: 'afterhours-hoodie', sku: 'NX-CLO-002', description: 'Свободный худи в выцветшем чёрном оттенке — комфортный слой для длинных городских дней.', name: 'AFTERHOURS HOODIE', category: 'Одежда', price: 8990, tag: 'НОВИНКА', image: '/images/afterhours-hoodie.jpg', color: 'Выцветший чёрный', sizes: ['S', 'M', 'L', 'XL'] },
  { id: 3, slug: 'offgrid-track-pant', sku: 'NX-CLO-003', description: 'Функциональные брюки в угольном цвете с лаконичным спортивным силуэтом.', name: 'OFFGRID TRACK PANT', category: 'Одежда', price: 7490, image: '/images/offgrid-pants.jpg', color: 'Угольный', sizes: ['S', 'M', 'L', 'XL'] },
  { id: 4, slug: 'street-form-01', sku: 'NX-SHO-004', description: 'Кроссовки в красно-белой цветовой комбинации — акцентная пара для городского образа.', name: 'STREET FORM 01', category: 'Обувь', price: 14990, image: '/images/street-form.jpg', color: 'Красный / белый', sizes: ['39', '40', '41', '42', '43'] },
  { id: 5, slug: 'no-signal-tee', sku: 'NX-CLO-005', description: 'Базовая футболка свободного кроя в белом цвете. Легко сочетается с повседневными образами.', name: 'NO SIGNAL TEE', category: 'Одежда', price: 3990, oldPrice: 4990, tag: '-20%', image: '/images/no-signal-tee.jpg', color: 'Белый', sizes: ['S', 'M', 'L', 'XL'] },
  { id: 6, slug: 'utility-crossbody', sku: 'NX-ACC-006', description: 'Компактная чёрная сумка через плечо для вещей, которые хочется держать под рукой.', name: 'UTILITY CROSSBODY', category: 'Аксессуары', price: 5990, image: '/images/utility-crossbody.jpg', color: 'Чёрный', sizes: ['ONE SIZE'] },
]
const categories = ['Все вещи', 'Обувь', 'Одежда', 'Аксессуары'] as const
const money = (value: number) => new Intl.NumberFormat('ru-RU').format(value) + ' ₽'
const paymentStatusLabel = (status: string) => ({
  paid: 'ОПЛАЧЕН',
  failed: 'НЕ ОПЛАЧЕН',
  refunded: 'ВОЗВРАТ',
  pending: 'ОЖИДАЕТ ОПЛАТЫ',
}[status] ?? 'ОЖИДАЕТ ОПЛАТЫ')
const productSlugFromPath = (pathname: string) => pathname.match(/^\/products\/([^/]+)\/?$/)?.[1] ?? null
const normalizeSearchText = (value: string) => value.toLocaleLowerCase('ru').replace(/ё/g, 'е').replace(/[^\p{L}\p{N}]+/gu, ' ').trim()

function matchesProductSearch(product: Product, query: string) {
  const normalizedQuery = normalizeSearchText(query)
  if (!normalizedQuery) return true
  const searchText = normalizeSearchText([
    product.name,
    product.slug,
    product.sku ?? '',
    product.category,
    product.color,
    product.description ?? '',
    ...product.sizes,
  ].join(' '))
  return normalizedQuery.split(/\s+/).every((word) => searchText.includes(word))
}

function readCart(): CartLine[] {
  try { return JSON.parse(localStorage.getItem('nexora-cart') ?? '[]') as CartLine[] } catch { return [] }
}

function readFavorites(): number[] {
  try { return JSON.parse(localStorage.getItem('nexora-favorites') ?? '[]') as number[] } catch { return [] }
}

export default function App() {
  const [catalog, setCatalog] = useState<Product[]>(demoProducts)
  const [activeCategory, setActiveCategory] = useState<string>('Все вещи')
  const [sort, setSort] = useState('featured')
  const [selectedSize, setSelectedSize] = useState('')
  const [selectedColor, setSelectedColor] = useState('')
  const [minimumPrice, setMinimumPrice] = useState('')
  const [maximumPrice, setMaximumPrice] = useState('')
  const [favoritesOnly, setFavoritesOnly] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [favorites, setFavorites] = useState<number[]>(readFavorites)
  const [cart, setCart] = useState<CartLine[]>(readCart)
  const cartRef = useRef(cart)
  const [cartOpen, setCartOpen] = useState(false)
  const [checkout, setCheckout] = useState(false)
  const [notice, setNotice] = useState('')
  const [checkoutError, setCheckoutError] = useState('')
  const [cartNeedsReview, setCartNeedsReview] = useState(false)
  const [paymentConfigured, setPaymentConfigured] = useState<boolean | null>(null)
  const [paymentUnavailableReason, setPaymentUnavailableReason] = useState('')
  const [accountOpen, setAccountOpen] = useState(false)
  const [accountOrders, setAccountOrders] = useState<Array<{ id: number; status: string; payment_status: string; total_amount: string; created_at: string; items: Array<{ product_id: number | null; selected_size: string | null; quantity: number }> }> | null>(null)
  const [accountError, setAccountError] = useState('')
  const [accountEmail, setAccountEmail] = useState('')
  const [accountPassword, setAccountPassword] = useState('')
  const [accountMode, setAccountMode] = useState<'login' | 'register'>('login')
  const [accountBusy, setAccountBusy] = useState(false)
  const [verificationPending, setVerificationPending] = useState(false)
  const [passwordResetRequested, setPasswordResetRequested] = useState(false)
  const [passwordResetNotice, setPasswordResetNotice] = useState('')
  const [passwordResetError, setPasswordResetError] = useState('')
  const [passwordResetBusy, setPasswordResetBusy] = useState(false)
  const [passwordResetToken, setPasswordResetToken] = useState<string | null>(() =>
    window.location.pathname === '/account/reset-password'
      ? new URLSearchParams(window.location.search).get('token') ?? ''
      : null,
  )
  const [passwordResetComplete, setPasswordResetComplete] = useState(false)
  const [passwordResetResult, setPasswordResetResult] = useState('')
  const [emailVerificationStatus, setEmailVerificationStatus] = useState<{
    verified: boolean
    notificationSent: boolean
    message: string
  } | null>(() => window.location.pathname === '/email/verified'
    ? { verified: false, notificationSent: false, message: 'Проверяем ссылку подтверждения…' }
    : null)
  const oauthCallbackStarted = useRef(false)
  const emailVerificationStarted = useRef(false)
  const passwordResetStarted = useRef(false)
  const paymentReturnOrderId = useRef(
    window.location.pathname === '/payment/return'
      ? new URLSearchParams(window.location.search).get('order_id')
      : null,
  )
  const [productSlug, setProductSlug] = useState(() => productSlugFromPath(window.location.pathname))
  useEffect(() => {
    let alive = true
    fetch('/api/payments/config')
      .then(async (response) => {
        if (!response.ok) throw new Error('Payment configuration request failed')
        return response.json() as Promise<{
          configured: boolean
          sales_enabled: boolean
          checkout_available: boolean
        }>
      })
      .then((result) => {
        if (alive) {
          setPaymentConfigured(result.checkout_available)
          setPaymentUnavailableReason(
            result.sales_enabled
              ? 'Оплата не настроена. Обратитесь к администратору магазина.'
              : 'Приём заказов отключён до подключения и проверки доставки СДЭК.',
          )
        }
      })
      .catch(() => {
        if (alive) setPaymentConfigured(null)
      })
    fetch('/api/products?limit=100')
      .then((response) => { if (!response.ok) throw new Error('API unavailable'); return response.json() as Promise<Array<Record<string, unknown>>> })
      .then((rows) => {
        if (!alive || rows.length === 0) return
        const products = rows.map((row) => ({
          id: Number(row.id), slug: String(row.slug), sku: String(row.sku ?? ''), description: String(row.description ?? ''),
          stockQuantity: Number(row.stock_quantity), name: String(row.name), category: String((row.category as { name?: string }).name ?? 'Одежда') as Product['category'],
          price: Number(row.price), oldPrice: row.compare_at_price ? Number(row.compare_at_price) : undefined, tag: row.compare_at_price ? 'ДРОП' : undefined,
          image: String(row.image_url ?? ''), images: Array.isArray(row.image_urls) ? row.image_urls.map(String) : undefined,
          stockBySize: row.stock_by_size && typeof row.stock_by_size === 'object' ? row.stock_by_size as Record<string, number> : undefined,
          color: String(row.color_name ?? ''), sizes: Array.isArray(row.sizes) ? row.sizes.map(String) : ['ONE SIZE'],
        }))
        setCatalog(products)
        let needsReview = false
        let changed = false
        const updated = cartRef.current.map((line) => {
            const product = products.find((item) => item.id === line.product.id)
            if (!product) {
              needsReview = true
              return line
            }
            const available = product.stockBySize?.[line.size] ?? product.stockQuantity
            const oldAvailable = line.product.stockBySize?.[line.size] ?? line.product.stockQuantity
            if (product.price !== line.product.price || available !== oldAvailable) needsReview = true
            changed = true
            return { ...line, product }
        })
        if (needsReview) setCartNeedsReview(true)
        if (changed) {
          cartRef.current = updated
          setCart(updated)
          localStorage.setItem('nexora-cart', JSON.stringify(updated))
        }
      }).catch(() => undefined)
    return () => { alive = false }
  }, [])
  useEffect(() => {
    if (window.location.pathname !== '/account/reset-password' || passwordResetStarted.current) return
    passwordResetStarted.current = true
    window.history.replaceState({}, '', '/account/reset-password')
  }, [])
  useEffect(() => {
    if (window.location.pathname !== '/payment/return') return
    const orderId = paymentReturnOrderId.current
    window.history.replaceState({}, '', '/')
    setNotice(
      orderId
        ? `Возврат с оплаты заказа №${orderId}. Проверенный статус доступен в личном кабинете.`
        : 'Вернулись со страницы оплаты. Проверь статус заказа в личном кабинете.',
    )
  }, [])
  useEffect(() => {
    if (window.location.pathname !== '/email/verified' || emailVerificationStarted.current) return
    emailVerificationStarted.current = true
    const token = new URLSearchParams(window.location.search).get('token')
    window.history.replaceState({}, '', '/email/verified')
    if (!token) {
      setEmailVerificationStatus({
        verified: false,
        notificationSent: false,
        message: 'В ссылке нет кода подтверждения. Запроси письмо повторно.',
      })
      return
    }

    void (async () => {
      try {
        const response = await fetch(`/api/auth/verify-email?token=${encodeURIComponent(token)}`)
        const result = await response.json() as {
          verified?: boolean
          notification_sent?: boolean
          message?: string
          detail?: string
        }
        if (!response.ok) throw new Error(result.detail ?? 'Ссылка недействительна или устарела.')
        setEmailVerificationStatus({
          verified: result.verified === true,
          notificationSent: result.notification_sent === true,
          message: result.message ?? 'Почта подтверждена.',
        })
      } catch (error) {
        setEmailVerificationStatus({
          verified: false,
          notificationSent: false,
          message: error instanceof Error ? error.message : 'Не удалось подтвердить email.',
        })
      }
    })()
  }, [])
  useEffect(() => {
    if (window.location.pathname !== '/oauth/callback' || oauthCallbackStarted.current) return
    oauthCallbackStarted.current = true
    setAccountOpen(true)
    setAccountOrders(null)
    setAccountError('')

    const params = new URLSearchParams(window.location.search)
    const code = params.get('code')
    const returnedState = params.get('state')
    const expectedState = sessionStorage.getItem('nexora-google-state')
    const codeVerifier = sessionStorage.getItem('nexora-google-verifier')
    const nonce = sessionStorage.getItem('nexora-google-nonce')
    sessionStorage.removeItem('nexora-google-state')
    sessionStorage.removeItem('nexora-google-verifier')
    sessionStorage.removeItem('nexora-google-nonce')
    window.history.replaceState({}, '', '/')

    if (!returnedState || returnedState !== expectedState) {
      setAccountError('Проверка безопасности Google не пройдена. Запусти вход ещё раз.')
      return
    }
    if (params.has('error')) {
      setAccountError('Вход через Google отменён или не выполнен.')
      return
    }
    if (!code || !codeVerifier || !nonce) {
      setAccountError('Ответ Google неполный. Запусти вход ещё раз.')
      return
    }

    void (async () => {
      setAccountBusy(true)
      try {
        const exchange = await fetch('/api/auth/google/exchange', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code, code_verifier: codeVerifier, nonce }),
        })
        if (!exchange.ok) {
          const result = await exchange.json() as { detail?: string }
          throw new Error(result.detail ?? 'Не удалось войти через Google.')
        }
        const token = (await exchange.json() as { access_token: string }).access_token
        localStorage.setItem('nexora-token', token)
        const orders = await fetch('/api/orders', { headers: { Authorization: `Bearer ${token}` } })
        if (!orders.ok) throw new Error('Вход выполнен, но историю заказов загрузить не удалось.')
        setAccountOrders(await orders.json())
        setAccountPassword('')
      } catch (error) {
        setAccountError(error instanceof Error ? error.message : 'Ошибка входа через Google.')
      } finally {
        setAccountBusy(false)
      }
    })()
  }, [])
  useEffect(() => {
    const product = catalog.find((item) => item.slug === productSlug)
    document.title = product ? `${product.name} — NEXORA` : 'NEXORA — Город твой подиум'
    const description = product?.description?.slice(0, 160) || 'NEXORA — одежда, кроссовки и аксессуары для собственного городского маршрута.'
    let meta = document.querySelector<HTMLMetaElement>('meta[name="description"]')
    if (!meta) {
      meta = document.createElement('meta')
      meta.name = 'description'
      document.head.append(meta)
    }
    meta.content = description
    let canonical = document.querySelector<HTMLLinkElement>('link[rel="canonical"]')
    if (!canonical) {
      canonical = document.createElement('link')
      canonical.rel = 'canonical'
      document.head.append(canonical)
    }
    canonical.href = `${window.location.origin}${product ? `/products/${encodeURIComponent(product.slug)}` : '/'}`
    const metadata: Array<[string, string]> = [
      ['og:title', document.title],
      ['og:description', description],
      ['og:type', product ? 'product' : 'website'],
      ['og:image', product?.images?.[0] || product?.image || '/images/rift-runner.jpg'],
      ['og:url', canonical.href],
    ]
    for (const [property, content] of metadata) {
      let tag = document.querySelector<HTMLMetaElement>(`meta[property="${property}"]`)
      if (!tag) {
        tag = document.createElement('meta')
        tag.setAttribute('property', property)
        document.head.append(tag)
      }
      tag.content = content
    }
  }, [catalog, productSlug])
  useEffect(() => {
    const syncProductRoute = () => setProductSlug(productSlugFromPath(window.location.pathname))
    window.addEventListener('popstate', syncProductRoute)
    return () => window.removeEventListener('popstate', syncProductRoute)
  }, [])
  const visibleProducts = useMemo(() => {
    const filtered = catalog.filter((product) => {
      const categoryMatches = activeCategory === 'Все вещи' || product.category === activeCategory
      const sizeMatches = !selectedSize || product.sizes.includes(selectedSize)
      const colorMatches = !selectedColor || product.color === selectedColor
      const minimumPriceMatches = !minimumPrice || product.price >= Number(minimumPrice)
      const maximumPriceMatches = !maximumPrice || product.price <= Number(maximumPrice)
      const favoriteMatches = !favoritesOnly || favorites.includes(product.id)
      return categoryMatches && sizeMatches && colorMatches && minimumPriceMatches && maximumPriceMatches
        && favoriteMatches && matchesProductSearch(product, searchQuery)
    })
    if (sort === 'cheap') return [...filtered].sort((a, b) => a.price - b.price)
    if (sort === 'expensive') return [...filtered].sort((a, b) => b.price - a.price)
    return filtered
  }, [activeCategory, catalog, favorites, favoritesOnly, maximumPrice, minimumPrice, searchQuery, selectedColor, selectedSize, sort])
  const availableSizes = useMemo(() => [...new Set(catalog.flatMap((product) => product.sizes))].sort((a, b) => a.localeCompare(b, 'ru', { numeric: true })), [catalog])
  const availableColors = useMemo(() => [...new Set(catalog.map((product) => product.color).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ru')), [catalog])
  const searchResults = useMemo(
    () => searchQuery.trim() ? catalog.filter((product) => matchesProductSearch(product, searchQuery)).slice(0, 6) : [],
    [catalog, searchQuery],
  )
  const cartCount = cart.reduce((sum, line) => sum + line.quantity, 0)
  const total = cart.reduce((sum, line) => sum + line.product.price * line.quantity, 0)
  const selectedProduct = catalog.find((product) => product.slug === productSlug)

  function saveCart(next: CartLine[]) { cartRef.current = next; setCart(next); localStorage.setItem('nexora-cart', JSON.stringify(next)) }
  function toggleFavorite(productId: number) {
    const next = favorites.includes(productId)
      ? favorites.filter((id) => id !== productId)
      : [...favorites, productId]
    setFavorites(next)
    localStorage.setItem('nexora-favorites', JSON.stringify(next))
  }
  function openProduct(product: Product) {
    window.history.pushState({}, '', `/products/${encodeURIComponent(product.slug)}`)
    setProductSlug(product.slug)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }
  function navigateToSection(section: string) {
    if (!productSlug) return
    window.history.pushState({}, '', `/#${section}`)
    setProductSlug(null)
    window.setTimeout(() => document.getElementById(section)?.scrollIntoView({ behavior: 'smooth' }), 0)
  }
  function returnToCatalog() {
    navigateToSection('catalog')
  }
  function addToCart(product: Product, size: string) {
    const currentQuantity = cart.filter((line) => line.product.id === product.id && line.size === size).reduce((sum, line) => sum + line.quantity, 0)
    const available = product.stockBySize?.[size] ?? product.stockQuantity
    if (available !== undefined && currentQuantity >= available) {
      setNotice(`Для размера ${size} доступно: ${available} шт.`)
      return
    }
    const found = cart.find((line) => line.product.id === product.id && line.size === size)
    saveCart(found ? cart.map((line) => line === found ? { ...line, quantity: line.quantity + 1 } : line) : [...cart, { product, size, quantity: 1 }])
    setCartOpen(true); setNotice('Добавлено в сумку')
  }
  function changeQuantity(index: number, delta: number) {
    const line = cart[index]
    const currentProduct = catalog.find((product) => product.id === line.product.id)
    const available = currentProduct?.stockBySize?.[line.size] ?? currentProduct?.stockQuantity
    if (delta > 0 && available !== undefined && line.quantity >= available) {
      setNotice(`Для размера ${line.size} доступно: ${available} шт.`)
      return
    }
    const next = cart.map((line, i) => i === index ? { ...line, quantity: line.quantity + delta } : line).filter((line) => line.quantity > 0)
    saveCart(next)
  }
  async function placeOrder(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setCheckoutError('')
    const form = new FormData(event.currentTarget)
    const email = String(form.get('email'))
    const password = String(form.get('password'))
    let createdOrderId: number | null = null
    try {
      for (const product of catalog) {
        for (const line of cart.filter((item) => item.product.id === product.id)) {
          const available = product.stockBySize?.[line.size] ?? product.stockQuantity
          if (available !== undefined && line.quantity > available) {
            throw new Error(`Для «${product.name}», размер ${line.size}, доступно ${available} шт. Измени количество в сумке.`)
          }
        }
      }
      if (cartNeedsReview) throw new Error('В корзине изменились цены или остатки. Проверь корзину и подтверди обновления.')
      let token = localStorage.getItem('nexora-token')
      if (!token) {
        let auth = await fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) })
        if (auth.status === 401) {
          auth = await fetch('/api/auth/register', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) })
          if (auth.ok) {
            setAccountEmail(email)
            setAccountMode('register')
            setVerificationPending(true)
            setAccountError('')
            setAccountOpen(true)
            setCheckout(false)
            return
          }
        }
        if (!auth.ok) {
          const result = await auth.json() as { detail?: string }
          if (auth.status === 403 || auth.status === 503) {
            setAccountEmail(email)
            setAccountMode(auth.status === 403 ? 'login' : 'register')
            setVerificationPending(true)
            setAccountError(result.detail ?? '')
            setAccountOpen(true)
            setCheckout(false)
            return
          }
          throw new Error(result.detail ?? 'Не удалось войти или создать аккаунт. Проверь email и пароль.')
        }
        token = (await auth.json() as { access_token: string }).access_token
        localStorage.setItem('nexora-token', token)
      }
      const headers = { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
      const freshness = await fetch('/api/cart', {
        method: 'PUT',
        headers,
        body: JSON.stringify({ items: cart.map((line) => ({ product_id: line.product.id, selected_size: line.size, quantity: line.quantity })) }),
      })
      if (!freshness.ok) {
        const result = await freshness.json() as { detail?: string }
        throw new Error(result.detail ?? 'Не удалось проверить актуальные остатки корзины.')
      }
      const currentCart = await freshness.json() as { items: Array<{ product_id: number; selected_size: string; quantity: number; unit_price: string | number; size_stock_quantity: number }> }
      const changedData = currentCart.items.some((line) => {
        const previous = cart.find((item) => item.product.id === line.product_id && item.size === line.selected_size)
        const oldStock = previous?.product.stockBySize?.[line.selected_size] ?? previous?.product.stockQuantity
        return Number(line.unit_price) !== previous?.product.price || oldStock !== line.size_stock_quantity
      })
      if (changedData) {
        const updatedCatalog = catalog.map((product) => {
          const currentLines = currentCart.items.filter((line) => line.product_id === product.id)
          const current = currentLines[0]
          return current ? {
            ...product,
            price: Number(current.unit_price),
            stockBySize: currentLines.reduce(
              (inventory, line) => ({ ...inventory, [line.selected_size]: line.size_stock_quantity }),
              { ...product.stockBySize },
            ),
          } : product
        })
        setCatalog(updatedCatalog)
        const updatedCart = cart.map((line) => {
          const product = updatedCatalog.find((item) => item.id === line.product.id)
          return product ? { ...line, product } : line
        })
        cartRef.current = updatedCart
        saveCart(updatedCart)
        setCartNeedsReview(true)
        setCheckout(false)
        setCartOpen(true)
        throw new Error('Цена или остаток товара изменились. Проверь обновлённые данные и подтверди изменения в корзине.')
      }
      const response = await fetch('/api/orders', { method: 'POST', headers, body: JSON.stringify({ shipping: {
        name: String(form.get('name')), address_line1: String(form.get('address')), city: String(form.get('city')),
        postal_code: String(form.get('postal_code')), country_code: 'RU',
      } }) })
      if (!response.ok) throw new Error('Заказ не создан. Проверь данные и остатки товара.')
      const order = await response.json() as { id: number }
      createdOrderId = order.id
      const paymentResponse = await fetch(`/api/orders/${order.id}/payment`, {
        method: 'POST',
        headers,
      })
      if (!paymentResponse.ok) {
        const result = await paymentResponse.json() as { detail?: string }
        throw new Error(result.detail ?? 'Заказ создан, но платёж не удалось начать.')
      }
      const payment = await paymentResponse.json() as { confirmation_url: string }
      saveCart([])
      window.location.assign(payment.confirmation_url)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Не удалось оформить заказ. Убедись, что backend запущен.'
      if (createdOrderId !== null) {
        saveCart([])
        setCheckout(false)
        setNotice(`Заказ №${createdOrderId} создан, но оплату не удалось открыть. Повтори попытку из личного кабинета.`)
        setAccountError(message)
        void openAccount()
      } else {
        setCheckoutError(message)
      }
    }
  }

  async function loadAccount(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setAccountError('')
    setAccountBusy(true)
    try {
      const endpoint = accountMode === 'register' ? '/api/auth/register' : '/api/auth/login'
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: accountEmail, password: accountPassword }),
      })
      if (!response.ok) {
        const result = await response.json() as { detail?: string }
        if (accountMode === 'register' && (response.status === 409 || response.status === 503)) {
          setVerificationPending(true)
        } else if (accountMode === 'login' && response.status === 403) {
          setVerificationPending(true)
        }
        throw new Error(result.detail ?? (accountMode === 'register' ? 'Не удалось создать аккаунт.' : 'Не удалось войти. Проверь email и пароль.'))
      }
      if (accountMode === 'register') {
        setVerificationPending(true)
        setAccountError('')
        return
      }
      const token = (await response.json() as { access_token: string }).access_token
      localStorage.setItem('nexora-token', token)
      const orders = await fetch('/api/orders', { headers: { Authorization: `Bearer ${token}` } })
      if (!orders.ok) throw new Error('Аккаунт создан, но историю заказов загрузить не удалось.')
      setAccountOrders(await orders.json())
      setAccountPassword('')
    } catch (error) {
      setAccountError(error instanceof Error ? error.message : 'Ошибка загрузки аккаунта.')
    } finally {
      setAccountBusy(false)
    }
  }

  async function resendVerificationEmail() {
    setAccountBusy(true)
    setAccountError('')
    try {
      const response = await fetch('/api/auth/resend-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: accountEmail }),
      })
      const result = await response.json() as { message?: string; detail?: string }
      if (!response.ok) throw new Error(result.detail ?? 'Не удалось отправить письмо.')
      setAccountError(result.message ?? 'Письмо отправлено.')
    } catch (error) {
      setAccountError(error instanceof Error ? error.message : 'Не удалось отправить письмо.')
    } finally {
      setAccountBusy(false)
    }
  }

  async function requestPasswordReset(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setPasswordResetBusy(true)
    setPasswordResetError('')
    setPasswordResetNotice('')
    try {
      const response = await fetch('/api/auth/password-reset/request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: accountEmail }),
      })
      const result = await response.json() as { message?: string; detail?: string }
      if (!response.ok) throw new Error(result.detail ?? 'Не удалось отправить письмо.')
      setPasswordResetNotice(result.message ?? 'Если аккаунт существует, письмо отправлено.')
    } catch (error) {
      setPasswordResetError(error instanceof Error ? error.message : 'Не удалось отправить письмо.')
    } finally {
      setPasswordResetBusy(false)
    }
  }

  async function completePasswordReset(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setPasswordResetBusy(true)
    setPasswordResetError('')
    setPasswordResetResult('')
    const form = new FormData(event.currentTarget)
    const password = String(form.get('password'))
    const confirmPassword = String(form.get('confirm_password'))
    if (password !== confirmPassword) {
      setPasswordResetError('Пароли не совпадают.')
      setPasswordResetBusy(false)
      return
    }
    if (!passwordResetToken) {
      setPasswordResetError('Ссылка сброса пароля недействительна или устарела.')
      setPasswordResetBusy(false)
      return
    }
    try {
      const response = await fetch('/api/auth/password-reset/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: passwordResetToken, new_password: password }),
      })
      const result = await response.json() as { message?: string; detail?: string }
      if (!response.ok) throw new Error(result.detail ?? 'Не удалось обновить пароль.')
      setPasswordResetComplete(true)
      setPasswordResetResult(result.message ?? 'Пароль обновлён. Теперь можно войти.')
    } catch (error) {
      setPasswordResetError(error instanceof Error ? error.message : 'Не удалось обновить пароль.')
    } finally {
      setPasswordResetBusy(false)
    }
  }

  async function startGoogleAuth() {
    setAccountError('')
    setAccountBusy(true)
    try {
      const configResponse = await fetch('/api/auth/google/config')
      if (!configResponse.ok) {
        const result = await configResponse.json() as { detail?: string }
        throw new Error(result.detail ?? 'Вход через Google пока не настроен.')
      }
      const config = await configResponse.json() as { client_id: string; redirect_uri: string }
      const randomValue = () => {
        const bytes = crypto.getRandomValues(new Uint8Array(32))
        return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
      }
      const verifier = randomValue() + randomValue().slice(0, 22)
      const state = randomValue()
      const nonce = randomValue()
      const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))
      const challenge = btoa(String.fromCharCode(...new Uint8Array(digest)))
        .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
      sessionStorage.setItem('nexora-google-state', state)
      sessionStorage.setItem('nexora-google-verifier', verifier)
      sessionStorage.setItem('nexora-google-nonce', nonce)
      const params = new URLSearchParams({
        client_id: config.client_id,
        redirect_uri: config.redirect_uri,
        response_type: 'code',
        scope: 'openid email profile',
        state,
        nonce,
        code_challenge: challenge,
        code_challenge_method: 'S256',
      })
      window.location.assign(`https://accounts.google.com/o/oauth2/v2/auth?${params}`)
    } catch (error) {
      setAccountError(error instanceof Error ? error.message : 'Не удалось начать вход через Google.')
      setAccountBusy(false)
    }
  }

  async function openAccount() {
    setAccountOpen(true)
    setAccountOrders(null)
    setAccountError('')
    setAccountMode('login')
    const token = localStorage.getItem('nexora-token')
    if (!token) return
    setAccountBusy(true)
    try {
      const response = await fetch('/api/orders', { headers: { Authorization: `Bearer ${token}` } })
      if (response.status === 401) {
        localStorage.removeItem('nexora-token')
        return
      }
      if (!response.ok) throw new Error('Не удалось загрузить историю заказов.')
      setAccountOrders(await response.json())
    } catch (error) {
      setAccountError(error instanceof Error ? error.message : 'Ошибка загрузки аккаунта.')
    } finally {
      setAccountBusy(false)
    }
  }

  async function retryPayment(orderId: number) {
    const token = localStorage.getItem('nexora-token')
    if (!token) return
    setAccountError('')
    try {
      const response = await fetch(`/api/orders/${orderId}/payment`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (response.status === 409) {
        const orders = await fetch('/api/orders', { headers: { Authorization: `Bearer ${token}` } })
        if (!orders.ok) throw new Error('Не удалось обновить статус оплаты.')
        setAccountOrders(await orders.json())
        return
      }
      const result = await response.json() as { confirmation_url?: string; detail?: string }
      if (!response.ok || !result.confirmation_url) {
        throw new Error(result.detail ?? 'Не удалось создать ссылку на оплату.')
      }
      window.location.assign(result.confirmation_url)
    } catch (error) {
      setAccountError(error instanceof Error ? error.message : 'Не удалось повторить оплату.')
    }
  }

  async function reorder(items: Array<{ product_id: number | null; selected_size: string | null; quantity: number }>) {
    const token = localStorage.getItem('nexora-token')
    if (!token) return
    let skipped = 0
    for (const item of items) {
      const product = catalog.find((row) => row.id === item.product_id)
      if (!product || !item.selected_size || (product.stockBySize?.[item.selected_size] ?? product.stockQuantity ?? 0) <= 0) {
        skipped += 1
        continue
      }
      const response = await fetch('/api/cart/items', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ product_id: item.product_id, selected_size: item.selected_size, quantity: Math.min(item.quantity, product.stockBySize?.[item.selected_size] ?? item.quantity, 20) }),
      })
      if (!response.ok) skipped += 1
    }
    if (skipped) setNotice(`${skipped} недоступных позиций пропущено при повторе заказа`)
    const cartResponse = await fetch('/api/cart', { headers: { Authorization: `Bearer ${token}` } })
    if (cartResponse.ok) {
      const serverCart = await cartResponse.json() as { items: Array<{ product_id: number; selected_size: string; quantity: number }> }
      const lines = serverCart.items.flatMap((line) => {
        const product = catalog.find((row) => row.id === line.product_id)
        return product ? [{ product, size: line.selected_size, quantity: line.quantity }] : []
      })
      saveCart(lines)
      setAccountOpen(false)
      setCartOpen(true)
    }
  }

  return <div className="site-shell" id="top">
    <div className="announcement"><span>НОВАЯ УЛИЧНАЯ ФОРМА</span><span>{paymentConfigured ? 'ОПЛАТА ЧЕРЕЗ ЮKASSA' : paymentConfigured === false ? 'ПРИЁМ ЗАКАЗОВ ОТКЛЮЧЁН' : 'ПРОВЕРКА НАСТРОЕК ОПЛАТЫ'}</span><span>DROP 01 / 2026</span></div>
    <header className="header">
      <a className="brand" href="#top" aria-label="NEXORA — наверх">NEX<span>O</span>RA<i>®</i></a>
      <nav className="main-nav" aria-label="Главная навигация"><a href="#catalog" onClick={(event) => { if (productSlug) { event.preventDefault(); navigateToSection('catalog') } }}>КАТАЛОГ</a><a href="#manifesto" onClick={(event) => { if (productSlug) { event.preventDefault(); navigateToSection('manifesto') } }}>МАНИФЕСТ</a><a href="#footer" onClick={(event) => { if (productSlug) { event.preventDefault(); navigateToSection('footer') } }}>КОНТАКТЫ</a></nav>
      <div className="header-actions"><button className="account-link" onClick={() => void openAccount()}>АККАУНТ</button><button className="search-link" onClick={() => setSearchOpen(!searchOpen)} aria-label="Поиск по каталогу" aria-expanded={searchOpen}>⌕</button><button className="bag-button" onClick={() => setCartOpen(true)}>СУМКА <b>{cartCount.toString().padStart(2, '0')}</b></button></div>
    </header>
    {searchOpen && <div className="search-panel-wrap"><div className="search-panel"><label htmlFor="catalog-search">ПОИСК ПО КАТАЛОГУ</label><input id="catalog-search" autoFocus value={searchQuery} onChange={(event) => { setSearchQuery(event.target.value); setActiveCategory('Все вещи') }} onKeyDown={(event) => { if (event.key === 'Escape') { setSearchOpen(false); setSearchQuery('') } else if (event.key === 'Enter' && searchResults[0]) { openProduct(searchResults[0]); setSearchOpen(false); setSearchQuery('') } }} placeholder="КРОССОВКИ, ХУДИ, СУМКА…"/><button onClick={() => { setSearchQuery(''); setSearchOpen(false) }} aria-label="Закрыть поиск">×</button></div>{searchQuery.trim() && <div className="search-results" role="region" aria-label="Результаты поиска">{searchResults.length ? searchResults.map((product) => <button className="search-result" key={product.id} aria-label={`Открыть товар ${product.name}`} onClick={() => { openProduct(product); setSearchOpen(false); setSearchQuery('') }}><span className="search-result-image" style={{ backgroundImage: product.image ? `url("${product.image}")` : undefined }}/><span className="search-result-info"><strong>{product.name}</strong><small>{product.category} · {product.color}</small></span><b>{money(product.price)}</b><span className="search-result-arrow">↗</span></button>) : <p className="search-empty">НИЧЕГО НЕ НАШЛОСЬ. ПОПРОБУЙ ДРУГОЕ НАЗВАНИЕ ИЛИ ЦВЕТ.</p>}</div>}</div>}

    <main>
      {selectedProduct ? <ProductDetail product={selectedProduct} onBack={returnToCatalog} onAdd={addToCart}/> : <>
      <section className="hero">
        <div className="hero-photo" role="img" aria-label="Уличный образ в кроссовках"><div className="hero-photo-shade"/><div className="hero-stamp">N° 001<br/>CITY UNIFORM</div><span className="hero-caption">ФОРМА ДЛЯ ТВОЕГО МАРШРУТА — С 2026</span></div>
        <div className="hero-copy"><p className="eyebrow"><i/> НЕ ПОДСТРАИВАЙСЯ. ДВИГАЙСЯ.</p><h1>ГОРОД<br/>ТВОЙ<br/><em>ПОДИУМ.</em></h1><p className="hero-lead">Одежда и кроссовки для тех, кто задаёт собственный темп. Без дресс-кода. Без лишнего шума.</p><a className="primary-cta" href="#catalog">ЗАБРАТЬ СВОЁ <span>↘</span></a><div className="hero-bottom"><span>DROP 01 — SS26</span><span>ОДЕЖДА / ОБУВЬ / АКСЕССУАРЫ</span></div></div>
        <div className="vertical-note">NEXORA® · EST. 2026</div>
        <div className="hero-index">01 <span>/</span> 03</div>
      </section>

      <section className="manifesto" id="manifesto"><span className="section-label">[ НАШ КОД ]</span><p>МЕНЬШЕ ПРАВИЛ.<br/><span>БОЛЬШЕ ТЕБЯ.</span></p><a href="#catalog">ПОСМОТРЕТЬ DROP <b>↗</b></a><span className="manifesto-mark">NX</span></section>

      <section className="catalog" id="catalog">
        <div className="catalog-heading"><div><p className="section-label">[ DROP 01 — SS26 ]</p><h2>ВЫХОДИ<br/><em>ИЗ РЯДА.</em></h2></div><p className="catalog-intro">Собрали базу, которая работает на тебя. Каждый день — новая версия.</p></div>
        <div className="catalog-toolbar"><div className="category-tabs">{categories.map((category) => <button key={category} className={activeCategory === category ? 'active' : ''} onClick={() => setActiveCategory(category)}>{category}</button>)}</div><label className="sort-control">СОРТИРОВКА <select value={sort} onChange={(event) => setSort(event.target.value)}><option value="featured">Сначала выбранное</option><option value="cheap">Сначала дешевле</option><option value="expensive">Сначала дороже</option></select></label></div>
        <div className="catalog-filterbar">
          <label className="catalog-filter">РАЗМЕР<select value={selectedSize} onChange={(event) => setSelectedSize(event.target.value)}><option value="">ЛЮБОЙ</option>{availableSizes.map((size) => <option key={size} value={size}>{size}</option>)}</select></label>
          <label className="catalog-filter">ЦВЕТ<select value={selectedColor} onChange={(event) => setSelectedColor(event.target.value)}><option value="">ЛЮБОЙ</option>{availableColors.map((color) => <option key={color} value={color}>{color}</option>)}</select></label>
          <fieldset className="price-filter"><legend>ЦЕНА, ₽</legend><label><span>ОТ</span><input aria-label="Минимальная цена" type="number" min="0" value={minimumPrice} onChange={(event) => setMinimumPrice(event.target.value)} placeholder="0"/></label><label><span>ДО</span><input aria-label="Максимальная цена" type="number" min={minimumPrice || 0} value={maximumPrice} onChange={(event) => setMaximumPrice(event.target.value)} placeholder="∞"/></label></fieldset>
          <button className={`favorites-filter ${favoritesOnly ? 'active' : ''}`} aria-pressed={favoritesOnly} onClick={() => setFavoritesOnly(!favoritesOnly)}>♡ ИЗБРАННОЕ <span>{favorites.length.toString().padStart(2, '0')}</span></button>
          {(selectedSize || selectedColor || minimumPrice || maximumPrice || favoritesOnly) && <button className="clear-filters" onClick={() => { setSelectedSize(''); setSelectedColor(''); setMinimumPrice(''); setMaximumPrice(''); setFavoritesOnly(false) }}>СБРОСИТЬ ×</button>}
        </div>
        {visibleProducts.length ? <div className="product-grid">{visibleProducts.map((product, index) => <article className="product-card" key={product.id}>
          <button className="product-image" onClick={() => openProduct(product)} aria-label={`Подробнее о товаре ${product.name}`} style={{ backgroundImage: `url("${product.image}")`, backgroundPosition: product.id === 3 ? "center 16%" : "center" }}><span className="product-number">0{index + 1} / 06</span>{product.tag && <span className="product-tag">{product.tag}</span>}<span className="quick-add">СМОТРЕТЬ ТОВАР <b>↗</b></span></button>
          <button className={`favorite ${favorites.includes(product.id) ? 'is-favorite' : ''}`} onClick={() => toggleFavorite(product.id)} aria-label={favorites.includes(product.id) ? 'Убрать из избранного' : 'В избранное'}>{favorites.includes(product.id) ? '♥' : '♡'}</button>
          <div className="product-meta"><span>{product.category.toUpperCase()} — {product.color.toUpperCase()}</span><h3><button className="product-title-link" onClick={() => openProduct(product)}>{product.name}</button></h3><div className="product-price">{money(product.price)}{product.oldPrice && <del>{money(product.oldPrice)}</del>}</div></div>
        </article>)}</div> : <div className="catalog-empty"><span>NX</span><p>НИЧЕГО НЕ НАШЛОСЬ ПО ЭТИМ ПАРАМЕТРАМ.</p><button onClick={() => { setActiveCategory('Все вещи'); setSelectedSize(''); setSelectedColor(''); setMinimumPrice(''); setMaximumPrice(''); setFavoritesOnly(false); setSearchQuery('') }}>СБРОСИТЬ ФИЛЬТРЫ ↗</button></div>}
        <div className="catalog-end"><span>ПОКАЗАНО {visibleProducts.length} ИЗ {catalog.length}</span><span>НОВАЯ ПОДБОРКА СКОРО <b>→</b></span></div>
      </section>

      <section className="newsletter"><div><p className="section-label">[ БУДЬ В ПОТОКЕ ]</p><h2>ПЕРВЫМ<br/>ЗНАЙ. <em>ПЕРВЫМ</em><br/>ЗАБИРАЙ.</h2></div><form onSubmit={(event) => { event.preventDefault(); setNotice('Это демо-форма: подписка не сохранена.'); }}><label htmlFor="email">ДРОПЫ, КОТОРЫЕ НЕ ЖДУТ. ОСТАВЬ ПОЧТУ.</label><div className="email-field"><input id="email" type="email" required placeholder="ТВОЙ EMAIL"/><button aria-label="Подписаться">↗</button></div><small>Никакого спама. Только новые дропы и важные новости.</small></form><span className="newsletter-spark">✳</span></section>
      </>}
    </main>

    <footer id="footer"><a className="brand" href="#top">NEX<span>O</span>RA<i>®</i></a><span>СОЗДАНО ДЛЯ ДВИЖЕНИЯ.</span><div><a href="mailto:hello@nexora.store">HELLO@NEXORA.STORE</a><a href="/admin">ДЛЯ КОМАНДЫ ↗</a><span>© 2026 NEXORA</span></div></footer>

    {cartOpen && <div className="overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) setCartOpen(false) }}><aside className="drawer" aria-label="Корзина"><div className="drawer-head"><div><span className="section-label">[ ТВОЙ ВЫБОР ]</span><h2>СУМКА <i>({cartCount})</i></h2></div><button className="close-button" onClick={() => setCartOpen(false)} aria-label="Закрыть">×</button></div>{cartNeedsReview && <div className="cart-review" role="alert">Цены или остатки изменились с момента добавления. Проверь актуальные данные перед оформлением.<button onClick={() => setCartNeedsReview(false)}>ПОДТВЕРДИТЬ ОБНОВЛЕНИЯ</button></div>}{cart.length === 0 ? <div className="empty-cart"><span>NX</span><p>Пока пусто.<br/>Но это легко исправить.</p><button onClick={() => setCartOpen(false)}>В КАТАЛОГ ↗</button></div> : <><div className="cart-lines">{cart.map((line, index) => <div className="cart-line" key={`${line.product.id}-${line.size}`}><div className="cart-thumb" style={{ backgroundImage: `url("${line.product.image}")` }}/><div className="cart-line-info"><span>{line.product.category.toUpperCase()} · РАЗМЕР {line.size}</span><strong>{line.product.name}</strong><b>{money(line.product.price)}</b><div className="quantity"><button onClick={() => changeQuantity(index, -1)} aria-label="Уменьшить">−</button><span>{line.quantity}</span><button onClick={() => changeQuantity(index, 1)} aria-label="Увеличить">+</button></div></div></div>)}</div><div className="cart-summary"><div><span>ИТОГО</span><strong>{money(total)}</strong></div><small>СДЭК пока не подключён. Доставка и её стоимость не оформляются.</small>{paymentConfigured !== true && <small role="alert">{paymentConfigured === false ? paymentUnavailableReason || 'Приём заказов отключён.' : 'Не удалось проверить настройки оплаты. Обновите страницу или обратитесь к администратору.'}</small>}<button className="primary-cta" disabled={cartNeedsReview || paymentConfigured !== true} onClick={() => { setNotice(''); setCheckout(true); setCartOpen(false) }}>ОФОРМИТЬ ЗАКАЗ <span>↗</span></button></div></>}</aside></div>}

    {checkout && <div className="modal-backdrop"><form className="checkout-modal" role="dialog" aria-modal="true" aria-labelledby="checkout-title" onSubmit={placeOrder}><button type="button" className="close-button" onClick={() => setCheckout(false)} aria-label="Закрыть">×</button><span className="section-label">[ ФИНИШНАЯ ПРЯМАЯ ]</span><h2 id="checkout-title">ОФОРМЛЕНИЕ<br/><em>ЗАКАЗА.</em></h2><p>После подтверждения перейдёшь на защищённую страницу ЮKassa.</p><label>ИМЯ<input required name="name" autoComplete="name" placeholder="Как к тебе обращаться"/></label><label>EMAIL<input required type="email" name="email" autoComplete="email" placeholder="name@example.com"/></label><label>ПАРОЛЬ ДЛЯ АККАУНТА<input required type="password" name="password" minLength={10} maxLength={128} autoComplete="new-password" placeholder="Минимум 10 символов"/></label><label>УЛИЦА И ДОМ<input required name="address" autoComplete="street-address" placeholder="Москва"/></label><div className="checkout-address-row"><label>ГОРОД<input required name="city" autoComplete="address-level2" placeholder="Москва"/></label><label>ИНДЕКС<input required name="postal_code" autoComplete="postal-code" placeholder="101000"/></label></div>{checkoutError && <p className="checkout-error" role="alert">{checkoutError}</p>}<div className="checkout-total"><span>К ОПЛАТЕ</span><b>{money(total)}</b></div><button className="primary-cta">ПЕРЕЙТИ К ОПЛАТЕ <span>↗</span></button></form></div>}

    {accountOpen && <div className="modal-backdrop"><section className="account-modal" role="dialog" aria-modal="true" aria-labelledby="account-title">
      <button className="close-button" onClick={() => setAccountOpen(false)} aria-label="Закрыть">×</button>
      <span className="section-label">[ ЛИЧНЫЙ КАБИНЕТ ]</span><h2 id="account-title">ИСТОРИЯ<br/><em>ЗАКАЗОВ.</em></h2>
      {accountOrders === null ? verificationPending ? <div className="verification-pending">
        <span className="verification-icon">✉</span><h3>ПРОВЕРЬ ПОЧТУ.</h3>
        <p>Мы отправили письмо на <strong>{accountEmail}</strong>. Перейди по ссылке из письма, чтобы подтвердить адрес и открыть аккаунт.</p>
        {accountError && <p role="status" className="verification-message">{accountError}</p>}
        <button className="primary-cta" onClick={() => void resendVerificationEmail()} disabled={accountBusy}>{accountBusy ? 'ОТПРАВЛЯЕМ…' : 'ОТПРАВИТЬ ПИСЬМО ЕЩЁ РАЗ ↗'}</button>
        <button className="account-signout" onClick={() => { setVerificationPending(false); setAccountError(''); setAccountMode('login') }}>ВЕРНУТЬСЯ КО ВХОДУ</button>
      </div> : passwordResetRequested ? <>
        <p className="account-hint">Укажи адрес аккаунта — отправим ссылку для создания нового пароля.</p>
        <form onSubmit={requestPasswordReset}>
          <label>EMAIL<input type="email" required autoComplete="email" value={accountEmail} onChange={(event) => setAccountEmail(event.target.value)}/></label>
          {passwordResetError && <p role="alert" className="checkout-error">{passwordResetError}</p>}
          {passwordResetNotice && <p role="status" className="verification-message">{passwordResetNotice}</p>}
          <button className="primary-cta" disabled={passwordResetBusy}>{passwordResetBusy ? 'ОТПРАВЛЯЕМ…' : 'ОТПРАВИТЬ ССЫЛКУ ↗'}</button>
        </form>
        <button className="account-signout" onClick={() => { setPasswordResetRequested(false); setPasswordResetNotice(''); setPasswordResetError('') }}>НАЗАД КО ВХОДУ</button>
      </> : <>
        <div className="account-tabs" role="tablist" aria-label="Действие с аккаунтом">
          <button type="button" className={accountMode === 'login' ? 'active' : ''} onClick={() => { setAccountMode('login'); setVerificationPending(false); setAccountError('') }}>ВОЙТИ</button>
          <button type="button" className={accountMode === 'register' ? 'active' : ''} onClick={() => { setAccountMode('register'); setVerificationPending(false); setAccountError('') }}>СОЗДАТЬ АККАУНТ</button>
        </div>
        <form onSubmit={loadAccount}>
          <label>EMAIL<input type="email" required autoComplete="email" value={accountEmail} onChange={(event) => setAccountEmail(event.target.value)}/></label>
          <label>ПАРОЛЬ<input type="password" required minLength={10} maxLength={128} autoComplete={accountMode === 'register' ? 'new-password' : 'current-password'} value={accountPassword} onChange={(event) => setAccountPassword(event.target.value)}/></label>
          {accountMode === 'register' && <small className="account-hint">Не менее 10 символов. После регистрации отправим ссылку для подтверждения email.</small>}
          {accountError && <p role="alert" className="checkout-error">{accountError}</p>}
          <button className="primary-cta" disabled={accountBusy}>{accountBusy ? 'ЗАГРУЗКА…' : accountMode === 'register' ? 'СОЗДАТЬ АККАУНТ ↗' : 'ВОЙТИ ↗'}</button>
        </form>
        {accountMode === 'login' && <button className="account-signout" onClick={() => { setPasswordResetRequested(true); setPasswordResetNotice(''); setPasswordResetError('') }}>ЗАБЫЛИ ПАРОЛЬ?</button>}
        <div className="account-divider"><span>ИЛИ</span></div>
        <button className="google-login" type="button" onClick={() => void startGoogleAuth()} disabled={accountBusy}><b>G</b> ПРОДОЛЖИТЬ С GOOGLE ↗</button>
      </> : accountBusy ? <p>Загружаем историю заказов…</p> : <>
        {accountError && <p role="alert" className="checkout-error">{accountError}</p>}
        {accountOrders.length ? <div className="account-orders">{accountOrders.map((order) => <article key={order.id}>
          <div><strong>ЗАКАЗ №{order.id}</strong><span>{new Date(order.created_at).toLocaleDateString('ru-RU')} · {order.status.toUpperCase()} · {paymentStatusLabel(order.payment_status)}</span></div>
          <p>{order.items.length} позиций · {money(Number(order.total_amount))}</p>
          {order.payment_status !== 'paid' && order.status !== 'cancelled' && <button onClick={() => void retryPayment(order.id)}>ОПЛАТИТЬ / ПОВТОРИТЬ ↗</button>}
          <button onClick={() => void reorder(order.items)}>ПОВТОРИТЬ ЗАКАЗ ↗</button>
        </article>)}</div> : <p>Заказов пока нет.</p>}
        <button className="account-signout" onClick={() => { localStorage.removeItem('nexora-token'); setAccountOrders(null); setAccountError(''); setAccountMode('login') }}>ВЫЙТИ ИЗ АККАУНТА</button>
      </>}
    </section></div>}
    {emailVerificationStatus && <main className="email-verification-screen">
      <a className="brand" href="/">NEX<span>O</span>RA<i>®</i></a>
      <section className={`email-verification-card ${emailVerificationStatus.verified ? 'is-verified' : 'is-invalid'}`}>
        <span className="verification-icon">{emailVerificationStatus.verified ? '✓' : '!'}</span>
        <span className="section-label">[ NEXORA · EMAIL ]</span>
        <h1>{emailVerificationStatus.verified ? <>ПОЧТА<br/><em>ПОДТВЕРЖДЕНА.</em></> : <>НЕ УДАЛОСЬ<br/><em>ПОДТВЕРДИТЬ.</em></>}</h1>
        <p>{emailVerificationStatus.message}</p>
        {emailVerificationStatus.verified && emailVerificationStatus.notificationSent && <small>Письмо с результатом отправлено на ваш адрес.</small>}
        <a className="primary-cta" href="/">ВЕРНУТЬСЯ В МАГАЗИН ↗</a>
      </section>
    </main>}
    {passwordResetToken !== null && <main className="email-verification-screen">
      <a className="brand" href="/">NEX<span>O</span>RA<i>®</i></a>
      <section className={`email-verification-card ${passwordResetComplete ? 'is-verified' : ''}`}>
        <span className="verification-icon">{passwordResetComplete ? '✓' : '↻'}</span>
        <span className="section-label">[ NEXORA · АККАУНТ ]</span>
        <h1>{passwordResetComplete ? <>ПАРОЛЬ<br/><em>ОБНОВЛЁН.</em></> : <>СОЗДАЙ<br/><em>НОВЫЙ ПАРОЛЬ.</em></>}</h1>
        {passwordResetComplete ? <><p>{passwordResetResult}</p><a className="primary-cta" href="/">ВЕРНУТЬСЯ И ВОЙТИ ↗</a></> : passwordResetToken ? <form className="password-reset-form" onSubmit={completePasswordReset}>
          <label>НОВЫЙ ПАРОЛЬ<input type="password" name="password" minLength={10} maxLength={128} required autoComplete="new-password"/></label>
          <label>ПОВТОРИ ПАРОЛЬ<input type="password" name="confirm_password" minLength={10} maxLength={128} required autoComplete="new-password"/></label>
          <small>Не менее 10 символов. Ссылка действует 1 час.</small>
          {passwordResetError && <p role="alert" className="checkout-error">{passwordResetError}</p>}
          <button className="primary-cta" disabled={passwordResetBusy}>{passwordResetBusy ? 'СОХРАНЯЕМ…' : 'СОХРАНИТЬ НОВЫЙ ПАРОЛЬ ↗'}</button>
        </form> : <><p>Ссылка сброса пароля недействительна или устарела.</p><a className="primary-cta" href="/">ВЕРНУТЬСЯ В МАГАЗИН ↗</a></>}
      </section>
    </main>}
    {notice && <button className="toast" onClick={() => setNotice('')}>{notice}<span>×</span></button>}
  </div>
}

function ProductDetail({ product, onBack, onAdd }: { product: Product; onBack: () => void; onAdd: (product: Product, size: string) => void }) {
  const [selectedSize, setSelectedSize] = useState('')
  const [selectedImage, setSelectedImage] = useState(0)
  const sizes = product.sizes.length ? product.sizes : ['ONE SIZE']
  const images = product.images?.length ? product.images : product.image ? [product.image] : []
  const sizeStock = selectedSize ? product.stockBySize?.[selectedSize] ?? product.stockQuantity : product.stockQuantity
  const isAvailable = sizeStock === undefined || sizeStock > 0

  useEffect(() => {
    setSelectedSize('')
    setSelectedImage(0)
  }, [product.id])

  return <section className="product-detail">
    <div className="product-breadcrumb"><button onClick={onBack}>КАТАЛОГ</button><span>/</span><span>{product.category.toUpperCase()}</span><span>/</span><span>{product.name}</span></div>
    <div className="product-detail-layout">
      <div className="product-gallery">
        <div className="product-detail-image" style={{ backgroundImage: images[selectedImage] ? `url("${images[selectedImage]}")` : undefined }} role="img" aria-label={`Фотография ${selectedImage + 1} товара ${product.name}`}>
          <span className="product-detail-index">NEXORA / DROP 01</span>
          {product.tag && <span className="product-tag">{product.tag}</span>}
        </div>
        {images.length > 1 && <div className="product-gallery-thumbnails" role="group" aria-label="Фотографии товара">{images.map((image, index) => <button type="button" key={`${image}-${index}`} className={index === selectedImage ? 'active' : ''} aria-label={`Показать фотографию ${index + 1}`} aria-pressed={index === selectedImage} onClick={() => setSelectedImage(index)} style={{ backgroundImage: `url("${image}")` }}/>)}</div>}
        <p className="product-image-caption">ГОРОДСКАЯ ФОРМА. ТВОЙ СОБСТВЕННЫЙ ТЕМП.</p>
      </div>
      <div className="product-purchase">
        <span className="product-detail-kicker">[ {product.category.toUpperCase()} / DROP 01 — SS26 ]</span>
        <h1>{product.name}</h1>
        <div className="product-detail-price">{money(product.price)}{product.oldPrice && <del>{money(product.oldPrice)}</del>}</div>
        <p className="product-detail-description">{product.description?.trim() || 'Вещь из коллекции NEXORA — создана для движения в собственном ритме.'}</p>
        <div className="product-detail-color"><span>ЦВЕТ</span><strong>{product.color || '—'}</strong></div>
        <div className="product-size-heading"><span>ВЫБЕРИ РАЗМЕР</span><span>АРТИКУЛ {product.sku || '—'}</span></div>
        <div className="product-detail-sizes" role="group" aria-label="Выбор размера">
          {sizes.map((size) => {
            const available = product.stockBySize?.[size] ?? product.stockQuantity
            return <button key={size} type="button" className={selectedSize === size ? 'selected' : ''} aria-label={`Размер ${size}${available === 0 ? ', нет в наличии' : ''}`} aria-pressed={selectedSize === size} disabled={available === 0} onClick={() => setSelectedSize(size)}>{size}</button>
          })}
        </div>
        <p className={`product-stock ${isAvailable ? '' : 'out-of-stock'}`}><i/>{sizeStock === undefined ? 'НАЛИЧИЕ УТОЧНЯЕТСЯ' : isAvailable ? `В НАЛИЧИИ${sizeStock < 5 ? ` · ОСТАЛОСЬ ${sizeStock}` : ''}` : 'ВРЕМЕННО НЕТ В НАЛИЧИИ'}</p>
        <button className="product-add-button" disabled={!selectedSize || !isAvailable} onClick={() => onAdd(product, selectedSize)}>{!isAvailable ? 'НЕТ В НАЛИЧИИ' : 'ДОБАВИТЬ В СУМКУ'} <span>↗</span></button>
        <div className="product-service">
          <article><span className="service-icon">↗</span><div><strong>ДОСТАВКА</strong><p>Магазин работает в демо-режиме: доставка пока не оформляется. Условия и сроки будут показаны при запуске реального заказа.</p></div></article>
          <article><span className="service-icon">↺</span><div><strong>ОБМЕН И ВОЗВРАТ</strong><p>До запуска продаж действуют только демонстрационные условия. Правила возврата будут опубликованы отдельно.</p></div></article>
          <article><span className="service-icon">✳</span><div><strong>ПОДРОБНО О ТОВАРЕ</strong><p>{product.category} · {product.color || 'цвет не указан'} · {sizes.join(' / ')}</p></div></article>
        </div>
        <button className="product-back-link" onClick={onBack}>← ВЕРНУТЬСЯ КО ВСЕМ ВЕЩАМ</button>
      </div>
    </div>
  </section>
}
