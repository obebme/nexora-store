import { useCallback, useEffect, useMemo, useState } from 'react'
import './admin.css'
import './admin-finishing.css'

type Category = { id: number; name: string; slug: string }
type Product = { id: number; category_id: number; sku: string; name: string; slug: string; category: Category; description: string | null; price: string; compare_at_price: string | null; currency_code: string; image_url: string | null; image_urls: string[]; color_name: string | null; sizes: string[]; stock_by_size: Record<string, number>; stock_quantity: number; is_active: boolean }
type Order = { id: number; status: string; payment_status: string; refund_status: string | null; reservation_expires_at: string | null; total_amount: string; currency_code: string; created_at: string; customer_email: string | null; shipping_name: string | null; shipping_address_line1: string | null; shipping_address_line2: string | null; shipping_city: string | null; shipping_region: string | null; shipping_postal_code: string | null; shipping_country_code: string | null; shipping_phone: string | null; items: Array<{ product_name: string; selected_size: string | null; quantity: number }> }
const statuses = ['pending', 'processing', 'shipped', 'delivered', 'cancelled']
const money = (amount: string) => `${new Intl.NumberFormat('ru-RU').format(Number(amount))} ₽`

export default function AdminApp() {
  const [token, setToken] = useState(localStorage.getItem('nexora-admin-token') ?? '')
  const [authorized, setAuthorized] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [imageSource, setImageSource] = useState<'url' | 'file'>('url')
  const [imageFile, setImageFile] = useState<File | null>(null)
  const [editingProduct, setEditingProduct] = useState<Product | null>(null)
  const [editImageSource, setEditImageSource] = useState<'url' | 'file'>('url')
  const [editImageFile, setEditImageFile] = useState<File | null>(null)
  const [products, setProducts] = useState<Product[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [orders, setOrders] = useState<Order[]>([])
  const [busy, setBusy] = useState(false)
  const [stockDrafts, setStockDrafts] = useState<Record<number, string>>({})
  const [orderSearch, setOrderSearch] = useState('')
  const [orderStatus, setOrderStatus] = useState('')
  const [orderFrom, setOrderFrom] = useState('')
  const [orderTo, setOrderTo] = useState('')
  const authHeaders = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }

  const filteredOrders = useMemo(() => orders.filter((order) => {
    const search = orderSearch.trim().toLocaleLowerCase('ru')
    const orderDate = order.created_at.slice(0, 10)
    return (!orderStatus || order.status === orderStatus)
      && (!orderFrom || orderDate >= orderFrom)
      && (!orderTo || orderDate <= orderTo)
      && (!search || [String(order.id), order.customer_email ?? '', order.shipping_name ?? '', order.shipping_address_line1 ?? '', order.shipping_city ?? ''].some((value) => value.toLocaleLowerCase('ru').includes(search)))
  }), [orderFrom, orderSearch, orderStatus, orderTo, orders])

  function parseStockBySize(raw: string, sizes: string[]) {
    const inventory: Record<string, number> = {}
    for (const entry of raw.split(',')) {
      const [size, count] = entry.split(':').map((part) => part.trim())
      if (size) inventory[size] = count === undefined ? Number.NaN : Number(count)
    }
    return Object.fromEntries(sizes.map((size) => [size, inventory[size] ?? 0]))
  }

  const load = useCallback(async (accessToken = token) => {
    const headers = { Authorization: `Bearer ${accessToken}` }
    const [productResponse, categoryResponse, orderResponse, meResponse] = await Promise.all([
      fetch('/api/admin/products', { headers }), fetch('/api/categories'), fetch('/api/admin/orders', { headers }), fetch('/api/auth/me', { headers }),
    ])
    if (meResponse.status === 403) throw new Error('Этот аккаунт не имеет роли администратора.')
    if (!productResponse.ok || !categoryResponse.ok || !orderResponse.ok || !meResponse.ok) throw new Error('Не удалось загрузить панель. Проверь backend и права администратора.')
    const [productRows, categoryRows, orderRows] = await Promise.all([productResponse.json(), categoryResponse.json(), orderResponse.json()]) as [Product[], Category[], Order[]]
    setProducts(productRows); setCategories(categoryRows); setOrders(orderRows); setAuthorized(true)
  }, [token])

  useEffect(() => {
    if (!token) return
    void load().catch((reason: unknown) => { setAuthorized(false); setError(reason instanceof Error ? reason.message : 'Ошибка доступа') })
  }, [token, load])

  async function signIn(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(''); setBusy(true)
    try {
      const response = await fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email, password }) })
      if (!response.ok) throw new Error('Не удалось войти. Проверь email и пароль администратора.')
      const result = await response.json() as { access_token: string }
      localStorage.setItem('nexora-admin-token', result.access_token); setToken(result.access_token)
      await load(result.access_token)
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Ошибка входа') }
    finally { setBusy(false) }
  }

  async function createProduct(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(''); setBusy(true)
    const formElement = event.currentTarget
    const form = new FormData(formElement)
    const sizes = String(form.get('sizes')).split(',').map((size) => size.trim()).filter(Boolean)
    try {
      let imageUrl = String(form.get('image_url') || '') || null
      if (imageSource === 'file') {
        if (!imageFile) throw new Error('Выбери файл изображения.')
        if (imageFile.size > 5 * 1024 * 1024) throw new Error('Размер изображения не должен превышать 5 МБ.')
        const uploadResponse = await fetch('/api/admin/uploads/images', {
          method: 'POST',
          headers: { Authorization: `******}`, 'Content-Type': imageFile.type },
          body: imageFile,
        })
        if (!uploadResponse.ok) {
          const result = await uploadResponse.json() as { detail?: string }
          throw new Error(result.detail ?? 'Не удалось загрузить изображение.')
        }
        imageUrl = (await uploadResponse.json() as { image_url: string }).image_url
      }
      const response = await fetch('/api/admin/products', { method: 'POST', headers: authHeaders, body: JSON.stringify({
        category_id: Number(form.get('category_id')), name: form.get('name'), sku: form.get('sku'), slug: form.get('slug'),
        description: form.get('description'), price: form.get('price'), compare_at_price: form.get('compare_at_price') || null,
        currency_code: 'RUB', stock_quantity: Number(form.get('stock_quantity')), image_url: imageUrl,
        color_name: form.get('color_name') || null, sizes, is_active: true,
      }) })
      if (!response.ok) throw new Error('Товар не создан. Проверь артикул, slug и категорию.')
      formElement.reset(); setImageFile(null); await load()
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Ошибка сохранения') }
    finally { setBusy(false) }
  }

  async function saveProduct(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!editingProduct) return
    setError(''); setBusy(true)
    const form = new FormData(event.currentTarget)
    const sizes = String(form.get('sizes')).split(',').map((size) => size.trim()).filter(Boolean)
    const stockBySize = parseStockBySize(String(form.get('stock_by_size') || ''), sizes)
    const galleryUrls = String(form.get('image_urls') || '').split(/\r?\n/).map((value) => value.trim()).filter(Boolean)
    try {
      if (Object.values(stockBySize).some((value) => !Number.isInteger(value) || value < 0)) {
        throw new Error('Укажи целое неотрицательное количество в формате S:2, M:4.')
      }
      let imageUrl = String(form.get('image_url') || '') || null
      if (editImageSource === 'file') {
        if (!editImageFile) throw new Error('Выбери файл изображения.')
        if (editImageFile.size > 5 * 1024 * 1024) throw new Error('Размер изображения не должен превышать 5 МБ.')
        const uploadResponse = await fetch('/api/admin/uploads/images', {
          method: 'POST',
          headers: { ...authHeaders, 'Content-Type': editImageFile.type },
          body: editImageFile,
        })
        if (!uploadResponse.ok) {
          const result = await uploadResponse.json() as { detail?: string }
          throw new Error(result.detail ?? 'Не удалось загрузить изображение.')
        }
        imageUrl = (await uploadResponse.json() as { image_url: string }).image_url
      }
      const response = await fetch(`/api/admin/products/${editingProduct.id}`, {
        method: 'PATCH',
        headers: authHeaders,
        body: JSON.stringify({
          category_id: Number(form.get('category_id')),
          name: form.get('name'),
          slug: form.get('slug'),
          sku: form.get('sku'),
          description: String(form.get('description') || ''),
          price: String(form.get('price')),
          compare_at_price: String(form.get('compare_at_price') || '') || null,
          stock_quantity: Object.values(stockBySize).reduce((sum, value) => sum + value, 0),
          stock_by_size: stockBySize,
          color_name: String(form.get('color_name') || ''),
          sizes,
          image_url: imageUrl,
          image_urls: [...new Set([imageUrl, ...galleryUrls].filter((value): value is string => Boolean(value)))],
        }),
      })
      if (!response.ok) {
        const result = await response.json() as { detail?: string }
        throw new Error(result.detail ?? 'Не удалось сохранить товар.')
      }
      setEditingProduct(null); setEditImageFile(null); await load()
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Ошибка сохранения товара') }
    finally { setBusy(false) }
  }

  async function updateProduct(productId: number, changes: { stock_quantity?: number; is_active?: boolean }) {
    const response = await fetch(`/api/admin/products/${productId}`, {
      method: 'PATCH', headers: authHeaders, body: JSON.stringify(changes),
    })
    if (!response.ok) { setError('Товар не обновлён. Проверь допустимые значения.'); return }
    await load()
  }

  async function updateStatus(orderId: number, status: string) {
    setError('')
    const response = await fetch(`/api/admin/orders/${orderId}/status`, { method: 'PATCH', headers: authHeaders, body: JSON.stringify({ status }) })
    if (!response.ok) { setError('Статус не обновлён. Возможно, заказ уже завершён.'); return }
    await load()
  }

  async function refundOrder(order: Order) {
    if (!window.confirm(`Оформить полный возврат ${money(order.total_amount)} по заказу №${order.id} через ЮKassa?`)) return
    setError('')
    setBusy(true)
    try {
      const response = await fetch(`/api/admin/orders/${order.id}/refund`, {
        method: 'POST',
        headers: authHeaders,
      })
      const result = await response.json() as { detail?: string }
      if (!response.ok) throw new Error(result.detail ?? 'Не удалось оформить возврат.')
      await load()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось оформить возврат.')
    } finally {
      setBusy(false)
    }
  }

  function signOut() { localStorage.removeItem('nexora-admin-token'); setToken(''); setAuthorized(false); setOrders([]); setProducts([]) }

  if (!authorized) return <main className="admin-login"><a className="admin-brand" href="/">NEX<span>O</span>RA <small>/ CONTROL</small></a><form onSubmit={signIn}><span className="admin-kicker">[ ПАНЕЛЬ УПРАВЛЕНИЯ ]</span><h1>ВХОД<br/><em>ДЛЯ КОМАНДЫ.</em></h1><label>EMAIL<input type="email" required value={email} onChange={(event) => setEmail(event.target.value)}/></label><label>ПАРОЛЬ<input type="password" required minLength={10} value={password} onChange={(event) => setPassword(event.target.value)}/></label>{error && <p className="admin-error">{error}</p>}<button className="admin-primary" disabled={busy}>{busy ? 'ВХОД…' : 'ОТКРЫТЬ ПАНЕЛЬ ↗'}</button><a href="/">← ВЕРНУТЬСЯ В МАГАЗИН</a></form></main>

  return <main className="admin-shell"><header className="admin-header"><a className="admin-brand" href="/">NEX<span>O</span>RA <small>/ CONTROL</small></a><div><span>АДМИНИСТРАТОР</span><button onClick={signOut}>ВЫЙТИ ↗</button></div></header><section className="admin-welcome"><div><span className="admin-kicker">[ ОПЕРАЦИОННАЯ ПАНЕЛЬ ]</span><h1>ДЕРЖИ<br/><em>ДВИЖЕНИЕ.</em></h1></div><div className="admin-stats"><article><span>ТОВАРЫ</span><b>{products.length}</b></article><article><span>ЗАКАЗЫ</span><b>{orders.length}</b></article><article><span>ОЖИДАЮТ</span><b>{orders.filter((order) => order.status === 'pending').length}</b></article></div></section>{error && <p className="admin-error admin-banner">{error}</p>}
    <section className="admin-section"><div className="admin-section-heading"><div><span className="admin-kicker">[ ИНВЕНТАРЬ ]</span><h2>ТОВАРЫ</h2></div><button className="admin-refresh" onClick={() => void load()}>ОБНОВИТЬ ↻</button></div><div className="admin-table-wrap"><table><thead><tr><th>ФОТО</th><th>ТОВАР</th><th>КАТЕГОРИЯ</th><th>АРТИКУЛ</th><th>ЦЕНА</th><th>ОСТАТОК</th><th>СТАТУС</th><th>ДЕЙСТВИЯ</th></tr></thead><tbody>{products.map((product) => <tr key={product.id}><td>{product.image_url ? <img className="admin-product-thumb" src={product.image_url} alt={product.name} loading="lazy"/> : <span className="admin-no-image">НЕТ ФОТО</span>}</td><td>{product.name}</td><td>{product.category.name}</td><td>{product.sku}</td><td>{money(product.price)}</td><td><input aria-label={`Остаток ${product.name}`} className="stock-edit" type="number" min="0" value={stockDrafts[product.id] ?? product.stock_quantity} onChange={(event) => setStockDrafts({ ...stockDrafts, [product.id]: event.target.value })}/></td><td>{product.is_active ? 'АКТИВЕН' : 'СКРЫТ'}</td><td><button className="table-action" onClick={() => void updateProduct(product.id, { stock_quantity: Number(stockDrafts[product.id] ?? product.stock_quantity) })}>СОХРАНИТЬ ОСТАТОК</button><button className="table-action" onClick={() => { setEditingProduct(product); setEditImageSource('url'); setEditImageFile(null) }}>РЕДАКТИРОВАТЬ</button><button className="table-action" onClick={() => void updateProduct(product.id, { is_active: !product.is_active })}>{product.is_active ? 'СКРЫТЬ' : 'ПОКАЗАТЬ'}</button></td></tr>)}</tbody></table></div>
      {editingProduct && <form key={editingProduct.id} className="admin-edit-product" onSubmit={saveProduct}><div className="admin-edit-heading"><div><span className="admin-kicker">[ РЕДАКТИРОВАНИЕ ]</span><h3>{editingProduct.name}</h3></div><button type="button" className="admin-edit-close" onClick={() => setEditingProduct(null)}>ЗАКРЫТЬ ×</button></div><div className="admin-product-form"><label>НАЗВАНИЕ<input name="name" required minLength={2} defaultValue={editingProduct.name}/></label><label>SLUG<input name="slug" required pattern="[a-z0-9-]+" defaultValue={editingProduct.slug}/></label><label>АРТИКУЛ<input name="sku" required defaultValue={editingProduct.sku}/></label><label>КАТЕГОРИЯ<select name="category_id" defaultValue={editingProduct.category_id}>{categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label><label>ЦЕНА, ₽<input name="price" required type="number" min="0" step="0.01" defaultValue={editingProduct.price}/></label><label>СТАРАЯ ЦЕНА<input name="compare_at_price" type="number" min="0" step="0.01" defaultValue={editingProduct.compare_at_price ?? ''}/></label><label>ОСТАТОК<input name="stock_quantity" required type="number" min="0" defaultValue={editingProduct.stock_quantity}/></label><label>РАЗМЕРЫ<input name="sizes" required defaultValue={editingProduct.sizes.join(', ')}/></label><label className="admin-span">ОСТАТКИ ПО РАЗМЕРАМ<input name="stock_by_size" defaultValue={Object.entries(editingProduct.stock_by_size ?? {}).map(([size, count]) => `${size}:${count}`).join(', ')} placeholder="S:2, M:4, L:1"/></label><label>ЦВЕТ<input name="color_name" defaultValue={editingProduct.color_name ?? ''}/></label><div className="admin-image-field admin-span"><span>ФОТО ТОВАРА</span><div className="admin-image-source"><button type="button" className={editImageSource === 'url' ? 'active' : ''} onClick={() => setEditImageSource('url')}>ПО ССЫЛКЕ</button><button type="button" className={editImageSource === 'file' ? 'active' : ''} onClick={() => setEditImageSource('file')}>С КОМПЬЮТЕРА</button></div>{editImageSource === 'url' ? <input aria-label="Основная фотография" name="image_url" type="text" defaultValue={editingProduct.image_url ?? ''} placeholder="https://example.com/photo.jpg"/> : <><input aria-label="Файл фотографии" type="file" accept="image/jpeg,image/png,image/gif,image/webp" onChange={(event) => setEditImageFile(event.target.files?.[0] ?? null)}/><small>JPEG, PNG, GIF или WebP · до 5 МБ</small></>}</div><label className="admin-span">ГАЛЕРЕЯ ФОТО — ССЫЛКИ ПО ОДНОЙ НА СТРОКУ<textarea name="image_urls" rows={3} defaultValue={(editingProduct.image_urls?.length ? editingProduct.image_urls : editingProduct.image_url ? [editingProduct.image_url] : []).join('\n')}/></label><label className="admin-span">ОПИСАНИЕ<textarea name="description" rows={3} defaultValue={editingProduct.description ?? ''}/></label><button className="admin-primary" disabled={busy}>СОХРАНИТЬ ИЗМЕНЕНИЯ ↗</button></div></form>}
    </section>
    <section className="admin-section"><div className="admin-section-heading"><div><span className="admin-kicker">[ НОВЫЙ ДРОП ]</span><h2>ДОБАВИТЬ ТОВАР</h2></div></div><form className="admin-product-form" onSubmit={createProduct}><label>НАЗВАНИЕ<input name="name" required minLength={2} placeholder="AFTERHOURS HOODIE"/></label><label>SLUG<input name="slug" required pattern="[a-z0-9-]+" placeholder="afterhours-hoodie"/></label><label>АРТИКУЛ<input name="sku" required placeholder="NX-CLO-004"/></label><label>КАТЕГОРИЯ<select name="category_id" required>{categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label><label>ЦЕНА, ₽<input name="price" required type="number" min="0" step="0.01"/></label><label>СТАРАЯ ЦЕНА<input name="compare_at_price" type="number" min="0" step="0.01"/></label><label>ОСТАТОК<input name="stock_quantity" required type="number" min="0" defaultValue="0"/></label><label>РАЗМЕРЫ<input name="sizes" required defaultValue="S, M, L, XL"/></label><label>ЦВЕТ<input name="color_name" placeholder="Чёрный"/></label><div className="admin-image-field admin-span"><span>ФОТО ТОВАРА</span><div className="admin-image-source"><button type="button" className={imageSource === 'url' ? 'active' : ''} onClick={() => setImageSource('url')}>ПО ССЫЛКЕ</button><button type="button" className={imageSource === 'file' ? 'active' : ''} onClick={() => setImageSource('file')}>С КОМПЬЮТЕРА</button></div>{imageSource === 'url' ? <input aria-label="Ссылка на фотографию" name="image_url" type="text" defaultValue="/images/no-signal-tee.jpg" placeholder="https://example.com/photo.jpg"/> : <><input aria-label="Файл фотографии" type="file" accept="image/jpeg,image/png,image/gif,image/webp" onChange={(event) => setImageFile(event.target.files?.[0] ?? null)}/><small>JPEG, PNG, GIF или WebP · до 5 МБ</small></>}</div><label className="admin-span">ОПИСАНИЕ<textarea name="description" rows={2}/></label><button className="admin-primary" disabled={busy}>СОХРАНИТЬ ТОВАР ↗</button></form></section>
    <section className="admin-section">
      <div className="admin-section-heading">
        <div><span className="admin-kicker">[ ОБРАБОТКА ]</span><h2>ЗАКАЗЫ</h2></div>
        <span className="admin-muted">ОПЛАТА ЮKASSA · ДОСТАВКА СДЭК НЕ НАСТРОЕНА</span>
      </div>
      <div className="admin-order-filters">
        <label>ПОИСК<input value={orderSearch} onChange={(event) => setOrderSearch(event.target.value)} placeholder="Номер, email, имя, адрес"/></label>
        <label>СТАТУС<select value={orderStatus} onChange={(event) => setOrderStatus(event.target.value)}><option value="">ВСЕ</option>{statuses.map((status) => <option key={status} value={status}>{status.toUpperCase()}</option>)}</select></label>
        <label>С ДАТЫ<input type="date" value={orderFrom} onChange={(event) => setOrderFrom(event.target.value)}/></label>
        <label>ПО ДАТУ<input type="date" value={orderTo} onChange={(event) => setOrderTo(event.target.value)}/></label>
      </div>
      {filteredOrders.length ? <div className="admin-order-list">{filteredOrders.map((order) => <article className="admin-order" key={order.id}>
        <div>
          <span className="admin-kicker">ЗАКАЗ №{order.id} · {new Date(order.created_at).toLocaleDateString('ru-RU')}</span>
          <strong>{order.items.map((item) => `${item.product_name} ×${item.quantity}${item.selected_size ? ` / ${item.selected_size}` : ''}`).join(' · ')}</strong>
          <small>{order.shipping_name ?? 'Клиент'} · {order.customer_email ?? 'email не указан'} · {order.shipping_phone ?? 'телефон не указан'}</small>
          <small>{[order.shipping_address_line1, order.shipping_address_line2, order.shipping_city, order.shipping_region, order.shipping_postal_code, order.shipping_country_code].filter(Boolean).join(', ') || 'Адрес не указан'}</small>
          <small>ОПЛАТА: {order.payment_status.toUpperCase()}{order.refund_status ? ` · ВОЗВРАТ: ${order.refund_status.toUpperCase()}` : ''}</small>
        </div>
        <b>{money(order.total_amount)}</b>
        <select aria-label={`Статус заказа ${order.id}`} value={order.status} disabled={['delivered', 'cancelled'].includes(order.status)} onChange={(event) => void updateStatus(order.id, event.target.value)}>{statuses.map((status) => <option key={status} value={status}>{status.toUpperCase()}</option>)}</select>
        {order.payment_status === 'paid' && <button className="table-action" disabled={busy} onClick={() => void refundOrder(order)}>ПОЛНЫЙ ВОЗВРАТ ↺</button>}
      </article>)}</div> : <div className="admin-empty">ЗАКАЗЫ ПО ЭТИМ ПАРАМЕТРАМ НЕ НАЙДЕНЫ.</div>}
    </section>
    <footer className="admin-footer">NEXORA CONTROL · ПОДГОТОВКА К PRODUCTION</footer></main>
}
