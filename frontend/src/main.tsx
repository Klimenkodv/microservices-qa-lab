import React from 'react'
import ReactDOM from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { AuthProvider } from './hooks/useAuth'
import { router } from './router'
import './styles/global.css'

ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><AuthProvider><RouterProvider router={router} /></AuthProvider></React.StrictMode>)
