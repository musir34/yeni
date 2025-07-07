# Replit.md - Güllü Shoes E-commerce Management System

## Overview

This is a comprehensive Flask-based e-commerce management system for Güllü Shoes, designed to handle order processing, inventory management, product catalogs, and business analytics. The system integrates with Trendyol marketplace API and provides advanced features like AI-powered stock prediction, automated label generation, and comprehensive reporting.

## System Architecture

### Backend Architecture
- **Framework**: Flask with SQLAlchemy ORM
- **Database**: PostgreSQL (Neon cloud-hosted)
- **Caching**: Redis for performance optimization
- **Authentication**: Flask-Login with role-based access control
- **API Integration**: Trendyol marketplace API for order and product synchronization
- **Background Processing**: APScheduler for automated tasks

### Frontend Architecture
- **Template Engine**: Jinja2 with custom filters
- **Static Assets**: CSS, JavaScript, and image files served from Flask
- **Real-time Updates**: Flask-SocketIO for live order status updates
- **Responsive Design**: Bootstrap-based UI components

## Key Components

### Order Management System
- **Multi-table Order Status**: Orders are tracked across 5 tables (Created, Picking, Shipped, Delivered, Cancelled)
- **Status Transitions**: Automated order status updates with API synchronization
- **Barcode/QR Code Generation**: Automated generation of shipping labels and tracking codes
- **Archive System**: Completed orders are moved to archive tables for performance

### Product Management
- **Catalog System**: Complete product catalog with images, specifications, and pricing
- **Stock Intelligence**: AI-powered stock prediction using Prophet forecasting
- **Label Generation**: Advanced product label system with QR codes and barcodes
- **Image Management**: Automated image processing and optimization

### Analytics & Reporting
- **Sales Analysis**: Multi-dimensional sales reporting with date ranges and filters
- **Profit Tracking**: Revenue and profit analysis across products and time periods
- **Stock Reports**: Inventory levels, reorder points, and stock movement tracking
- **User Activity Logs**: Comprehensive audit trail of user actions

### External Integrations
- **Trendyol API**: Full integration for order sync, product updates, and stock management
- **OpenAI API**: AI-powered text analysis and stock prediction
- **Exchange Rate API**: Real-time currency conversion for pricing
- **Redis Cache**: Performance optimization for frequently accessed data

## Data Flow

### Order Processing Flow
1. Orders are fetched from Trendyol API and stored in `OrderCreated` table
2. Orders move through status tables (Created → Picking → Shipped → Delivered)
3. Each status change triggers API updates back to Trendyol
4. Completed orders are archived for historical tracking

### Product Synchronization
1. Products are fetched from Trendyol API and stored in `Product` table
2. Stock levels are monitored and updated in real-time
3. Product images are downloaded and optimized automatically
4. Price updates are synchronized bidirectionally

### Analytics Pipeline
1. Sales data is aggregated from all order status tables
2. Prophet ML model analyzes historical sales patterns
3. Stock predictions are generated based on sales velocity
4. Reports are cached in Redis for performance

## External Dependencies

### APIs
- **Trendyol Marketplace API**: Order management, product sync, stock updates
- **OpenAI API**: AI-powered analytics and text processing
- **Exchange Rate API**: Currency conversion for international pricing

### Third-party Libraries
- **Prophet**: Time series forecasting for stock prediction
- **Pillow**: Image processing and optimization
- **ReportLab**: PDF generation for catalogs and reports
- **QRCode**: QR code generation for products and orders
- **Pandas**: Data analysis and manipulation
- **NumPy**: Numerical computations for analytics

### Infrastructure
- **PostgreSQL (Neon)**: Primary database with connection pooling
- **Redis**: Caching layer for performance optimization
- **Flask-Caching**: Application-level caching with configurable TTL

## Deployment Strategy

### Environment Configuration
- **Development**: Local SQLite with debug mode enabled
- **Production**: Neon PostgreSQL with Redis caching
- **Environment Variables**: API keys, database URLs, and secrets managed via environment

### Database Management
- **Migrations**: Manual schema updates with SQLAlchemy
- **Backup Strategy**: Automated backups via Neon cloud infrastructure
- **Performance**: Indexed queries and connection pooling

### Scaling Considerations
- **Horizontal Scaling**: Blueprint-based modular architecture
- **Caching Strategy**: Redis for frequently accessed data
- **Database Optimization**: Query optimization and indexing

## User Preferences

Preferred communication style: Simple, everyday language.

## Recent Changes

- **July 07, 2025**: Modified authentication system to allow home page access without login
  - Added home route (`/`) to authentication bypass list
  - Added `home.home` endpoint to allowed routes
  - Home page now opens directly when application starts

## Changelog

Changelog:
- July 06, 2025. Initial setup
- July 07, 2025. Updated home page access configuration