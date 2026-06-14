import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'
import { PipelineProvider } from './context/PipelineContext.jsx'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <PipelineProvider>
      <App />
    </PipelineProvider>
  </React.StrictMode>,
)
