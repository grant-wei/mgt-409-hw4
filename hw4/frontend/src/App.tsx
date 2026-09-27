import { useEffect, useState, type FormEvent, type MouseEvent, type SyntheticEvent } from 'react'
import catalogueData from './data/products.json'
import './App.css'

type Product = {
  product_id: string
  name: string
  garment_type: string
  description: string
  colors: string[]
  search_tags: string[]
  image_path: string
  price: number
  inventory: { size: string; quantity: number }[]
}

type ChatProductCard = Pick<Product, 'product_id' | 'name' | 'description' | 'price' | 'image_path'>
type ProductComparison = {
  product_id: string
  name: string
  price: number
  colors: string[]
  available_sizes: string[]
}
type ChatMessage = {
  role: 'user' | 'assistant'
  text: string
  products?: ChatProductCard[]
  comparison?: ProductComparison[]
}

const products = catalogueData as Product[]
const RECENTLY_VIEWED_KEY = 'campus_customs_recently_viewed'
const money = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 2,
})

function ProductImage({
  src,
  alt,
  className,
  loading,
}: {
  src: string
  alt: string
  className?: string
  loading?: 'lazy' | 'eager'
}) {
  const [blendMode, setBlendMode] = useState<'multiply' | 'screen'>('multiply')

  function detectPhotoBackdrop(event: SyntheticEvent<HTMLImageElement>) {
    const image = event.currentTarget
    try {
      const canvas = document.createElement('canvas')
      canvas.width = 8
      canvas.height = 8
      const context = canvas.getContext('2d', { willReadFrequently: true })
      if (!context) return
      context.drawImage(image, 0, 0, 8, 8)
      const pixels = context.getImageData(0, 0, 8, 8).data
      let darkEdgePixels = 0
      for (let y = 0; y < 8; y += 1) {
        for (let x = 0; x < 8; x += 1) {
          if (x !== 0 && x !== 7 && y !== 0 && y !== 7) continue
          const offset = (y * 8 + x) * 4
          if ((pixels[offset] + pixels[offset + 1] + pixels[offset + 2]) / 3 < 58) darkEdgePixels += 1
        }
      }
      setBlendMode(darkEdgePixels >= 8 ? 'screen' : 'multiply')
    } catch {
      setBlendMode('multiply')
    }
  }

  const imageClassName = [
    className,
    blendMode === 'screen' ? 'dark-source' : '',
    src.includes('benjamin-franklin-1-4-zip') ? 'crop-side-bars' : '',
  ].filter(Boolean).join(' ')
  return <img className={imageClassName} src={src} alt={alt} loading={loading} onLoad={detectPhotoBackdrop} style={{ mixBlendMode: blendMode }} />
}

function ChatMessageBody({ text }: { text: string }) {
  return <>{text.split(/\r?\n/).map((line, lineIndex) => {
    const bullet = line.match(/^\s*[-*]\s+(.*)$/)
    const content = bullet ? bullet[1] : line
    const formatted = content.split(/(\*\*[^*]+\*\*)/g).map((part, partIndex) =>
      part.startsWith('**') && part.endsWith('**')
        ? <strong key={partIndex}>{part.slice(2, -2)}</strong>
        : part,
    )
    return <span className={bullet ? 'chat-copy-bullet' : 'chat-copy-line'} key={lineIndex}>
      {bullet && <span aria-hidden="true">•</span>}{formatted}
    </span>
  })}</>
}

function routeFor(pathname: string) {
  const productMatch = pathname.match(/^\/products\/([^/]+)\/?$/)
  if (productMatch) return { page: 'detail', productId: decodeURIComponent(productMatch[1]) }
  if (pathname === '/products' || pathname === '/products/') return { page: 'products' }
  if (pathname === '/about' || pathname === '/about/') return { page: 'about' }
  if (pathname === '/login' || pathname === '/login/') return { page: 'login' }
  if (pathname === '/create-account' || pathname === '/create-account/') return { page: 'account' }
  return { page: 'home' }
}

function App() {
  const [pathname, setPathname] = useState(window.location.pathname)
  const [nameSearch, setNameSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [sizeFilter, setSizeFilter] = useState('')
  const [availabilityFilter, setAvailabilityFilter] = useState('')
  const [recentlyViewedIds, setRecentlyViewedIds] = useState<string[]>(() => {
    try {
      const stored = JSON.parse(window.localStorage.getItem(RECENTLY_VIEWED_KEY) || '[]') as unknown
      return Array.isArray(stored)
        ? stored.filter((id): id is string => typeof id === 'string' && products.some((product) => product.product_id === id)).slice(0, 6)
        : []
    } catch {
      return []
    }
  })
  const route = routeFor(pathname)

  useEffect(() => {
    const updatePath = () => setPathname(window.location.pathname)
    window.addEventListener('popstate', updatePath)
    return () => window.removeEventListener('popstate', updatePath)
  }, [])

  function navigate(event: MouseEvent<HTMLAnchorElement>, href: string) {
    event.preventDefault()
    window.history.pushState({}, '', href)
    setPathname(href)
    window.scrollTo({ top: 0, behavior: 'auto' })
  }

  const linkProps = (href: string) => ({
    href,
    onClick: (event: MouseEvent<HTMLAnchorElement>) => navigate(event, href),
  })

  const selectedProduct = route.page === 'detail'
    ? products.find((product) => product.product_id === route.productId)
    : undefined

  useEffect(() => {
    const productId = selectedProduct?.product_id
    if (!productId) return
    setRecentlyViewedIds((current) => {
      const next = [productId, ...current.filter((id) => id !== productId)].slice(0, 6)
      try {
        window.localStorage.setItem(RECENTLY_VIEWED_KEY, JSON.stringify(next))
      } catch {
        // The current session still keeps recent items if storage is unavailable.
      }
      return next
    })
  }, [selectedProduct?.product_id])

  const typeOptions = [...new Set(products.map((product) => product.garment_type))].sort((a, b) => a.localeCompare(b))
  const sizeOptions = [...new Set(products.flatMap((product) => product.inventory.map((item) => item.size)))].sort((a, b) => a.localeCompare(b))
  const filteredProducts = products.filter((product) => {
    if (nameSearch && !product.name.toLocaleLowerCase().includes(nameSearch.toLocaleLowerCase())) return false
    if (typeFilter && product.garment_type !== typeFilter) return false
    if (sizeFilter && !product.inventory.some((item) => item.size === sizeFilter)) return false
    const selectedSize = sizeFilter
      ? product.inventory.find((item) => item.size === sizeFilter)
      : undefined
    if (availabilityFilter === 'in-stock') {
      return selectedSize ? selectedSize.quantity > 0 : product.inventory.some((item) => item.quantity > 0)
    }
    if (availabilityFilter === 'out-of-stock') {
      return selectedSize ? selectedSize.quantity === 0 : product.inventory.every((item) => item.quantity === 0)
    }
    return true
  })
  const recentlyViewed = recentlyViewedIds
    .map((id) => products.find((product) => product.product_id === id))
    .filter((product): product is Product => !!product)
  const homePicks = products.slice(0, 3)
  const heroProduct = products.find((product) => product.product_id === 'basic-hoodie-big-yale') ?? products[0]

  return (
    <div className="site-shell">
      <header className="site-header">
        <a className="wordmark" {...linkProps('/')} aria-label="Campus Customs home">
          <span className="brand-mark" aria-hidden="true">CC</span>
          <span className="brand-name">Campus Customs<span>Yale apparel</span></span>
        </a>
        <nav className="main-nav" aria-label="Main navigation">
          <a className={route.page === 'home' ? 'current' : undefined} aria-current={route.page === 'home' ? 'page' : undefined} {...linkProps('/')}>Home</a>
          <a className={route.page === 'products' || route.page === 'detail' ? 'current' : undefined} aria-current={route.page === 'products' || route.page === 'detail' ? 'page' : undefined} {...linkProps('/products')}>Products</a>
          <a className={route.page === 'about' ? 'current' : undefined} aria-current={route.page === 'about' ? 'page' : undefined} {...linkProps('/about')}>About Us</a>
          <a className={route.page === 'login' ? 'current' : undefined} aria-current={route.page === 'login' ? 'page' : undefined} {...linkProps('/login')}>Log in</a>
          <a className={`account-link${route.page === 'account' ? ' current' : ''}`} aria-current={route.page === 'account' ? 'page' : undefined} {...linkProps('/create-account')}>Create account</a>
        </nav>
      </header>

      {route.page === 'products' && (
        <main className="page-content">
          <div className="page-heading">
            <p className="eyebrow">Campus Customs</p>
            <h1>Products</h1>
            <p className="result-count">{filteredProducts.length} of {products.length} products</p>
          </div>
          <section className="catalogue-tools" aria-label="Find products">
            <label>
              Search by name
              <input value={nameSearch} onChange={(event) => setNameSearch(event.target.value)} placeholder="Search products" />
            </label>
            <label>
              Type
              <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
                <option value="">All types</option>
                {typeOptions.map((type) => <option key={type} value={type}>{type}</option>)}
              </select>
            </label>
            <label>
              Size
              <select value={sizeFilter} onChange={(event) => setSizeFilter(event.target.value)}>
                <option value="">All sizes</option>
                {sizeOptions.map((size) => <option key={size} value={size}>{size}</option>)}
              </select>
            </label>
            <label>
              Availability
              <select value={availabilityFilter} onChange={(event) => setAvailabilityFilter(event.target.value)}>
                <option value="">Any availability</option>
                <option value="in-stock">In stock</option>
                <option value="out-of-stock">Out of stock</option>
              </select>
            </label>
            <button className="clear-filters" type="button" onClick={() => {
              setNameSearch('')
              setTypeFilter('')
              setSizeFilter('')
              setAvailabilityFilter('')
            }}>Clear filters</button>
          </section>
          {recentlyViewed.length > 0 && (
            <section className="recent-section" aria-label="Recently viewed">
              <div className="section-heading"><h2>Recently viewed</h2></div>
              <div className="product-grid recent-grid">
                {recentlyViewed.map((product) => (
                  <a className="product-card" key={product.product_id} {...linkProps(`/products/${encodeURIComponent(product.product_id)}`)}>
                    <div className="product-card-image"><ProductImage src={product.image_path} alt={product.name} loading="lazy" /></div>
                    <div className="product-card-copy">
                      <div className="product-card-title"><h2>{product.name}</h2><span>{money.format(product.price)}</span></div>
                      <p>{product.description}</p>
                    </div>
                  </a>
                ))}
              </div>
            </section>
          )}
          {filteredProducts.length ? (
            <section className="product-grid" aria-label="Products">
              {filteredProducts.map((product) => (
                <a className="product-card" key={product.product_id} {...linkProps(`/products/${encodeURIComponent(product.product_id)}`)}>
                  <div className="product-card-image"><ProductImage src={product.image_path} alt={product.name} loading="lazy" /></div>
                  <div className="product-card-copy">
                    <div className="product-card-title"><h2>{product.name}</h2><span>{money.format(product.price)}</span></div>
                    <p>{product.description}</p>
                  </div>
                </a>
              ))}
            </section>
          ) : <p className="empty-products" role="status">No products match those filters.</p>}
        </main>
      )}

      {route.page === 'detail' && selectedProduct && (
        <main className="page-content product-detail-page">
          <a className="back-link" {...linkProps('/products')}>← Products</a>
          <article className="product-detail">
            <div className="detail-image">
              <ProductImage src={selectedProduct.image_path} alt={selectedProduct.name} loading="eager" />
            </div>
            <div className="detail-copy">
              <p className="eyebrow">{selectedProduct.garment_type}</p>
              <h1>{selectedProduct.name}</h1>
              <p className="detail-price">{money.format(selectedProduct.price)}</p>
              <p className="detail-description">{selectedProduct.description}</p>
              <div className="detail-section">
                <h2>Colors</h2>
                <p>{selectedProduct.colors.join(', ')}</p>
              </div>
              <div className="detail-section">
                <h2>Sizes and stock</h2>
                <ul className="stock-list">
                  {selectedProduct.inventory.map((item) => (
                    <li key={item.size}>
                      <span>{item.size}</span>
                      <span>{item.quantity > 0 ? `${item.quantity} in stock` : 'Out of stock'}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </article>
        </main>
      )}

      {route.page === 'detail' && !selectedProduct && (
        <main className="page-content not-found">
          <a className="back-link" {...linkProps('/products')}>← Products</a>
          <h1>Product not found</h1>
        </main>
      )}

      {route.page === 'home' && (
        <main className="home-page" aria-label="Home">
          <section className="home-hero">
            <div className="home-hero-copy">
              <p className="eyebrow">Campus Customs · New Haven</p>
              <h1>Yale gear for people who like Yale.</h1>
              <a className="primary-link" {...linkProps('/products')}>Shop the collection <span aria-hidden="true">↗</span></a>
              <div className="hero-note"><span className="hero-note-line" /><span>Campus classics, made to be worn.</span></div>
            </div>
            <div className="home-hero-art">
              <span className="hero-art-label">YALE · CAMPUS CUSTOMS</span>
              <ProductImage src={heroProduct.image_path} alt={heroProduct.name} loading="eager" />
              <a className="hero-product-tag" {...linkProps(`/products/${encodeURIComponent(heroProduct.product_id)}`)}>
                <span><small>Campus classic</small><strong>{heroProduct.name}</strong></span>
                <b>{money.format(heroProduct.price)}</b>
              </a>
            </div>
          </section>
          <div className="home-ribbon" aria-label="Campus Customs collections">
            <span>YALE BLUE</span><i aria-hidden="true">✳</i><span>COLLEGIATE CLASSICS</span><i aria-hidden="true">✳</i><span>NEW HAVEN</span>
          </div>
          <section className="home-featured">
            <div className="section-heading home-section-heading">
              <div><p className="eyebrow">Find your next favorite</p><h2>Shop the collection</h2></div>
              <a className="text-link" {...linkProps('/products')}>View all products <span aria-hidden="true">→</span></a>
            </div>
            <div className="product-grid home-product-grid">
              {homePicks.map((product, index) => (
                <a className="product-card" key={product.product_id} {...linkProps(`/products/${encodeURIComponent(product.product_id)}`)}>
                  <div className="product-card-image"><span className="product-index">0{index + 1}</span><ProductImage src={product.image_path} alt={product.name} loading="lazy" /></div>
                  <div className="product-card-copy">
                    <div className="product-card-title"><h2>{product.name}</h2><span>{money.format(product.price)}</span></div>
                    <p>{product.description}</p>
                  </div>
                </a>
              ))}
            </div>
          </section>
        </main>
      )}

      {route.page === 'about' && (
        <main className="about-page" aria-label="About Us">
          <div className="about-marker" aria-hidden="true"><span>CC</span><i>NEW HAVEN · YALE</i></div>
          <p className="site-copy">Campus Customs began in 1975. Our store is on Broadway in New Haven. We ship orders.</p>
        </main>
      )}

      {route.page === 'login' && <AuthPage mode="login" />}
      {route.page === 'account' && <AuthPage mode="register" />}

      <ShopChat onNavigate={navigate} />
    </div>
  )
}

function AuthPage({ mode }: { mode: 'login' | 'register' }) {
  const isRegister = mode === 'register'
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [feedback, setFeedback] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFeedback(null)
    setIsSubmitting(true)

    const endpoint = isRegister ? '/api/auth/register' : '/api/auth/login'
    const payload = isRegister
      ? { first_name: firstName, last_name: lastName, email, password }
      : { email, password }

    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(typeof result.detail === 'string' ? result.detail : 'Could not complete this request.')
      }
      setPassword('')
      setFeedback({ kind: 'success', text: isRegister ? 'Account created.' : 'Logged in.' })
      window.dispatchEvent(new Event('campus-customs-auth-change'))
    } catch (error) {
      setFeedback({ kind: 'error', text: error instanceof Error ? error.message : 'Could not connect to the account service.' })
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <p className="eyebrow">Campus Customs</p>
        <h1>{isRegister ? 'Create account' : 'Log in'}</h1>

        {isRegister && (
          <>
            <label>
              First name
              <input autoComplete="given-name" maxLength={80} required value={firstName} onChange={(event) => setFirstName(event.target.value)} />
            </label>
            <label>
              Last name
              <input autoComplete="family-name" maxLength={80} required value={lastName} onChange={(event) => setLastName(event.target.value)} />
            </label>
          </>
        )}

        <label>
          Email
          <input autoComplete="email" autoCapitalize="none" maxLength={254} required type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
        </label>
        <label>
          Password
          <input autoComplete={isRegister ? 'new-password' : 'current-password'} minLength={isRegister ? 8 : undefined} maxLength={1024} required type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>

        {feedback && (
          <p className={`auth-feedback ${feedback.kind}`} role={feedback.kind === 'error' ? 'alert' : 'status'}>
            {feedback.text}
          </p>
        )}

        <button className="auth-submit" type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Please wait' : isRegister ? 'Create account' : 'Log in'}
        </button>
      </form>
    </main>
  )
}

function ShopChat({
  onNavigate,
}: {
  onNavigate: (event: MouseEvent<HTMLAnchorElement>, href: string) => void
}) {
  const [isOpen, setIsOpen] = useState(false)
  const [message, setMessage] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isSending, setIsSending] = useState(false)

  useEffect(() => {
    let active = true
    const loadHistory = async () => {
      try {
        const response = await fetch('/api/chat/history', { credentials: 'same-origin' })
        if (!response.ok) return
        const result = await response.json() as { messages?: ChatMessage[] }
        if (active) setMessages(result.messages || [])
      } catch {
        // Chat remains available if history cannot be loaded.
      }
    }
    const refreshHistory = () => { void loadHistory() }
    void loadHistory()
    window.addEventListener('campus-customs-auth-change', refreshHistory)
    return () => {
      active = false
      window.removeEventListener('campus-customs-auth-change', refreshHistory)
    }
  }, [])

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = message.trim()
    if (!trimmed || isSending) return
    setMessages((current) => [...current, { role: 'user', text: trimmed }])
    setMessage('')
    setIsSending(true)
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        credentials: 'same-origin',
        signal: AbortSignal.timeout(85000),
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: trimmed, current_page: window.location.pathname }),
      })
      const result = await response.json().catch(() => ({})) as Partial<{
        reply: string
        products: ChatProductCard[]
        comparison: ProductComparison[]
        detail: string
      }>
      if (!response.ok) {
        throw new Error(typeof result.detail === 'string' ? result.detail : 'The shop chat could not get a response. Try again.')
      }
      setMessages((current) => [...current, {
        role: 'assistant',
        text: result.reply || '',
        products: result.products || [],
        comparison: result.comparison || [],
      }])
    } catch (error) {
      setMessages((current) => [...current, {
        role: 'assistant',
        text: error instanceof DOMException && ['TimeoutError', 'AbortError'].includes(error.name)
          ? 'Shop chat timed out. Please try again.'
          : error instanceof TypeError
            ? 'The shop chat could not get a response. Try again.'
          : error instanceof Error ? error.message : 'The shop chat could not get a response. Try again.',
      }])
    } finally {
      setIsSending(false)
    }
  }

  return (
    <aside className="chat-widget">
      {isOpen && (
        <section className="chat-panel" aria-label="Shop chat">
          <div className="chat-panel-heading">
            <h2>Shop chat</h2>
            <button className="chat-close" type="button" onClick={() => setIsOpen(false)} aria-label="Close chat">×</button>
          </div>
          <div className="chat-messages" aria-live="polite">
            {messages.length === 0 ? <p>Chat is ready.</p> : messages.map((item, index) => (
              <div className="chat-turn" key={`${index}-${item.role}`}>
                <div className={`chat-message ${item.role}`}><ChatMessageBody text={item.text} /></div>
                {!!item.products?.length && (
                  <div className="chat-result-cards" aria-label="Product matches">
                    {item.products.map((product) => {
                      const detailPath = `/products/${encodeURIComponent(product.product_id)}`
                      return (
                        <a
                          className="chat-result-card"
                          href={detailPath}
                          key={product.product_id}
                          onClick={(event) => onNavigate(event, detailPath)}
                        >
                          <ProductImage src={product.image_path} alt={product.name} loading="lazy" />
                          <span className="chat-result-card-copy">
                            <span className="chat-result-card-heading">
                              <strong>{product.name}</strong>
                              <span>{money.format(product.price)}</span>
                            </span>
                            <span className="chat-result-card-description">{product.description}</span>
                          </span>
                        </a>
                      )
                    })}
                  </div>
                )}
                {item.comparison?.length === 2 && (
                  <section className="chat-comparison" aria-label="Product comparison">
                    <h3>Side-by-side comparison</h3>
                    <div className="comparison-grid">
                      {item.comparison.map((product) => {
                        const detailPath = `/products/${encodeURIComponent(product.product_id)}`
                        return (
                          <article className="comparison-item" key={product.product_id}>
                            <h4>{product.name}</h4>
                            <dl>
                              <div><dt>Price</dt><dd>{money.format(product.price)}</dd></div>
                              <div><dt>Colors</dt><dd>{product.colors.join(', ') || 'Not listed'}</dd></div>
                              <div><dt>Available sizes</dt><dd>{product.available_sizes.join(', ') || 'None in stock'}</dd></div>
                            </dl>
                            <a href={detailPath} onClick={(event) => onNavigate(event, detailPath)}>View product</a>
                          </article>
                        )
                      })}
                    </div>
                  </section>
                )}
              </div>
            ))}
          </div>
          <form className="chat-form" onSubmit={sendMessage}>
            <input aria-label="Message" value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Type a message" disabled={isSending} />
            <button type="submit" disabled={isSending || !message.trim()}>{isSending ? 'Sending' : 'Send'}</button>
          </form>
        </section>
      )}
      <button className="chat-toggle" type="button" onClick={() => setIsOpen((current) => !current)} aria-expanded={isOpen}>
        {isOpen ? 'Close chat' : 'Chat'}
      </button>
    </aside>
  )
}

export default App
