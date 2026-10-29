import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import AdminApp from './Admin'
import './theme.css'

const Root = window.location.pathname.startsWith('/admin') ? AdminApp : App

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
)
