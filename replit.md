# Overview

This is a comprehensive e-commerce management system built for a shoe retailer called "Güllü Shoes". The application manages orders, products, inventory, and customer interactions through a Flask-based web application with PostgreSQL database integration via Neon hosting. The system integrates heavily with the Trendyol marketplace API for order management and product synchronization.

# System Architecture

## Frontend Architecture
- **Framework**: Flask with Jinja2 templating
- **UI Components**: Bootstrap-based responsive design
- **Client-side**: JavaScript for dynamic interactions, AJAX for API calls
- **PDF Generation**: ReportLab for catalogs and labels
- **Barcode/QR Generation**: python-barcode and qrcode libraries

## Backend Architecture
- **Framework**: Flask with Blueprint-based modular structure
- **Language**: Python 3.11
- **Architecture Pattern**: MVC with Blueprint separation
- **Authentication**: Flask-Login with role-based access control
- **Session Management**: Flask sessions with permanent session support

## Data Storage Solutions
- **Primary Database**: PostgreSQL hosted on Neon
- **Cache Layer**: Redis via Upstash for session and data caching
- **Static Files**: Local file system for images, barcodes, and generated files
- **File Uploads**: Local storage with secure filename handling

# Key Components

## Order Management System
- **Multi-table Architecture**: Separate tables for each order status (Created, Picking, Shipped, Delivered, Cancelled)
- **Status Transitions**: Automated order status progression with API integration
- **Webhook Integration**: Real-time order updates from Trendyol marketplace
- **Archive System**: Historical order data preservation

## Product Management
- **Inventory Tracking**: Real-time stock levels synchronized with Trendyol
- **Product Variants**: Color and size variant management
- **Image Management**: Automated product image downloading and storage
- **Barcode System**: Automatic barcode and QR code generation

## Analytics and Reporting
- **Sales Analysis**: Comprehensive sales reporting with date filtering
- **Stock Management**: Intelligent stock level monitoring and alerts
- **Profit Tracking**: Revenue and cost analysis
- **AI Integration**: OpenAI integration for predictive analytics and text analysis

## User Management
- **Role-based Access**: Multi-level user permissions (admin, operator, viewer)
- **Activity Logging**: Comprehensive user action tracking
- **2FA Support**: TOTP-based two-factor authentication

# Data Flow

## Order Processing Flow
1. Orders received from Trendyol API webhook
2. Initial order stored in OrderCreated table
3. Manual or automated progression through status tables
4. Barcode and shipping label generation
5. Status updates pushed back to Trendyol API
6. Completed orders archived for historical analysis

## Product Synchronization Flow
1. Product data fetched from Trendyol API
2. Local product database updated with inventory levels
3. Images downloaded and stored locally
4. Stock levels monitored and updated
5. Low stock alerts generated
6. Stock updates pushed back to Trendyol API

## User Interaction Flow
1. User authentication with optional 2FA
2. Role-based dashboard presentation
3. CRUD operations logged and cached
4. Real-time updates via AJAX
5. Session management with Redis cache

# External Dependencies

## Third-party APIs
- **Trendyol Seller API**: Primary marketplace integration
- **OpenAI API**: AI-powered analytics and text processing
- **Exchange Rate API**: Currency conversion for pricing

## Python Libraries
- **Core**: Flask, SQLAlchemy, psycopg2-binary
- **Authentication**: Flask-Login, pyotp, Werkzeug
- **HTTP**: aiohttp, requests
- **Data Processing**: pandas, numpy
- **Document Generation**: ReportLab, Pillow
- **Barcode/QR**: python-barcode, qrcode
- **Caching**: Flask-Caching, redis
- **Scheduling**: APScheduler for background tasks

## Infrastructure Services
- **Database**: Neon PostgreSQL
- **Cache**: Upstash Redis
- **Hosting**: Replit with automatic deployment
- **Version Control**: Git with automatic commits

# Deployment Strategy

## Environment Configuration
- **Development**: Local development with SQLite fallback
- **Production**: Neon PostgreSQL with Redis caching
- **Environment Variables**: Secure credential management
- **Auto-deployment**: Git-based continuous deployment

## Scaling Considerations
- **Database**: Connection pooling and query optimization
- **Cache**: Redis for session and frequently accessed data
- **File Storage**: Static file optimization and CDN readiness
- **API Rate Limiting**: Built-in rate limiting for external API calls

## Monitoring and Logging
- **Application Logs**: Structured logging with rotation
- **Error Tracking**: Comprehensive exception handling
- **Performance Monitoring**: Database query optimization
- **User Activity**: Detailed audit trail

# Changelog
- June 24, 2025. Initial setup

# User Preferences

Preferred communication style: Simple, everyday language.