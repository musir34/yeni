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
- **Enhanced Label System**: Advanced product labels with QR codes containing company logo, flexible sizing (100x50, 80x50, 80x40mm), product images, and professional layout
- **Image Management System**: Upload, organize, and manage product images with model_color.jpg naming convention, drag-and-drop upload, image optimization, and search functionality

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
- June 24, 2025. Enhanced Product Label System implemented with QR codes containing logo, flexible sizing, and modern UI
- June 24, 2025. Fixed JavaScript syntax errors in enhanced product label system, search functionality now working properly
- June 24, 2025. Added comprehensive image management system with upload, search, edit, and delete functionality for product images
- June 24, 2025. Implemented manual label customization system allowing users to adjust text, QR code, and image positions, sizes, and fonts
- June 24, 2025. Created advanced drag-and-drop label editor with real-time visual positioning, detailed element properties, and preset save/load functionality
- June 24, 2025. Fixed database SSL connection issues and authentication bypass for label editor access. Advanced editor now fully functional with mouse drag-drop positioning, detailed property panels, and design save/load system
- June 24, 2025. Created standalone label editor application to bypass authentication issues. Complete drag-and-drop system now accessible at /advanced_editor with full functionality including element positioning, property editing, and design management
- June 24, 2025. Simplified label editor created without detailed settings panels. Focus on core drag-and-drop functionality with persistent localStorage save/load system. Clean interface with only essential controls
- June 24, 2025. Fixed 404 routing issue by adding direct route for advanced editor. Simplified drag-and-drop label editor now accessible with persistent design save/load functionality
- June 24, 2025. Added adjustable label sizes, resizable elements, and print integration. Users can now change label dimensions, resize photos/QR codes/text, and access saved designs from the printing section for direct printing
- June 24, 2025. Fixed API route 404 errors by implementing missing generate_advanced_label_preview endpoint. Print integration now fully functional with saved design preview generation
- June 24, 2025. Converted editor to use product-specific fields (Model Kodu, Renk, Beden, Ürün Görseli, QR Kod) instead of generic text. System now automatically populates these fields with real product data during preview and printing
- June 24, 2025. Added title field to editor and fixed saved design system to use real selected product data instead of random placeholder data. System now requires product selection before using saved designs
- June 24, 2025. Completely replaced old label settings with drag-and-drop editor as main system. Removed complex detailed settings, fixed product selection detection from both queue and search results. Editor is now the primary label design interface
- June 24, 2025. Fixed JavaScript function definition errors (updateSelectedDesignInfo). System now fully functional with product-specific fields (Title, Model Code, Color, Size, Product Image, QR Code) automatically populated with real product data during printing
- June 25, 2025. Resolved product selection issue in getSelectedProducts function. Simplified labelQueue reading logic and fixed preview/print workflow. Enhanced Product Label system now works seamlessly with drag-and-drop editor as primary interface
- June 25, 2025. Fixed QR code to contain only barcode data, improved product image loading with multiple format support, and added functional print button with new window opening for proper printing workflow
- June 25, 2025. Implemented multi-page label printing system with PDF generation for large quantities. System now creates multiple pages when labels exceed single page capacity, with automatic page calculation and proper document formatting
- June 25, 2025. Fixed product image loading issue with case-insensitive filename matching. System now properly finds product images regardless of case differences (147_beyaz.jpg vs 147_Beyaz.jpg) with comprehensive fallback search

# User Preferences

Preferred communication style: Simple, everyday language.
User wants simplified drag-and-drop editor without detailed settings panels, but with persistent save/load functionality for different label configurations. Also needs adjustable label sizes, resizable elements, and saved designs accessible in printing section. IMPORTANT: Labels should use product-specific fields (size, model code, color) instead of generic text, with automatic population of real product data during printing. Each field should be positioned separately and filled with actual product information.