# Güllü Shoes E-Commerce Management System

## Overview

This is a comprehensive e-commerce management system built for Güllü Shoes, a Turkish footwear company. The system integrates with Trendyol (a major Turkish e-commerce platform) to manage orders, products, inventory, and business analytics. The application is built with Flask and uses PostgreSQL as the primary database, with Redis for caching.

## System Architecture

### Backend Architecture
- **Framework**: Flask (Python web framework)
- **Database**: PostgreSQL (Neon hosted)
- **Caching**: Redis with Flask-Caching
- **API Integration**: Trendyol API for order and product management
- **Authentication**: Flask-Login with role-based access control
- **Task Processing**: Background tasks with APScheduler

### Frontend Architecture
- **Template Engine**: Jinja2 templates
- **Static Assets**: CSS, JavaScript, images served from static directory
- **UI Components**: Bootstrap-based responsive design
- **Label Generation**: PIL/Pillow for dynamic label and barcode generation

## Key Components

### Order Management System
- **Multi-Table Architecture**: Orders are tracked across different status tables:
  - `OrderCreated` - New orders
  - `OrderPicking` - Orders being prepared
  - `OrderShipped` - Shipped orders
  - `OrderDelivered` - Delivered orders
  - `OrderCancelled` - Cancelled orders
- **Status Transitions**: Orders move between tables as their status changes
- **Barcode Integration**: Automatic barcode generation for orders and products

### Product Management
- **Product Catalog**: Complete product information with images, sizes, colors
- **Inventory Tracking**: Real-time stock levels synchronized with Trendyol
- **Product Labels**: Dynamic label generation with QR codes and barcodes
- **Image Management**: Product image upload and optimization

### Analytics and Intelligence
- **Sales Analysis**: Multi-dimensional sales reporting and analytics
- **AI Stock Prediction**: Machine learning-based inventory forecasting using Prophet
- **Profit Analysis**: Revenue and profit tracking with detailed breakdowns
- **Intelligent Stock Analyzer**: Smart stock level recommendations

### Integration Services
- **Trendyol API**: Complete integration for orders, products, and inventory
- **Return Management**: Processing of returns and exchanges
- **Commission Tracking**: Excel-based commission updates
- **Webhook Services**: Real-time data synchronization (currently disabled)

## Data Flow

1. **Order Processing**:
   - Orders fetched from Trendyol API
   - Stored in appropriate status table
   - Processed through barcode scanning workflow
   - Status updates sent back to Trendyol

2. **Product Management**:
   - Products synchronized from Trendyol
   - Images and metadata managed locally
   - Stock levels updated bidirectionally

3. **Analytics Pipeline**:
   - Sales data aggregated from multiple order tables
   - AI models trained on historical data
   - Predictions and recommendations generated

## External Dependencies

### Core Dependencies
- **Flask Ecosystem**: Flask, Flask-SQLAlchemy, Flask-Login, Flask-Caching
- **Database**: PostgreSQL with psycopg2-binary
- **API Integration**: aiohttp for async HTTP requests
- **Image Processing**: Pillow for image manipulation
- **Barcode Generation**: python-barcode, qrcode
- **PDF Generation**: ReportLab for catalogs and reports
- **ML/Analytics**: Prophet, NumPy, Pandas, Plotly
- **AI Integration**: OpenAI API for intelligent analysis

### Third-Party Services
- **Trendyol API**: Primary e-commerce platform integration
- **Neon PostgreSQL**: Cloud database hosting
- **Redis**: Caching layer
- **OpenAI**: AI-powered analytics and predictions

## Deployment Strategy

### Environment Configuration
- Environment variables for API keys and database connections
- Separate configurations for development and production
- SSL/TLS enforcement for database connections

### Database Strategy
- PostgreSQL with connection pooling
- Automatic table creation and migration support
- Backup and recovery procedures

### Caching Strategy
- Redis-based caching for frequently accessed data
- Configurable cache timeouts by data type
- Cache invalidation on data updates

### Monitoring and Logging
- Comprehensive logging across all modules
- Error tracking and performance monitoring
- User activity logging for audit trails

## Changelog

- July 06, 2025. Initial setup
- July 06, 2025. Added product creation feature
  - Extended Product model with Trendyol-required fields (description, brand, category, dimensions, etc.)
  - Created new product creation page at /product_create
  - Added API endpoints for product creation and marketplace integration
  - Implemented image upload functionality for products
  - Added "Yeni Ürün Ekle" menu item under "Ürün İşlemleri"
  - Products can be created locally first, then sent to marketplaces (Trendyol, etc.) when ready

## User Preferences

Preferred communication style: Simple, everyday language.