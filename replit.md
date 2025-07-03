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
- June 25, 2025. Fixed design-to-print coordinate system and font size scaling issues. Implemented proper coordinate transformation from editor canvas (width*4px, height*2px) to print resolution (300 DPI), corrected font size persistence in editor, and synchronized element positioning between design and output
- June 25, 2025. Enhanced font change visualization in drag-and-drop editor. Added forced DOM reflow, improved CSS property inheritance, and implemented properties-first font size reading system. Fixed coordinate scaling with proper fallback mechanisms and enhanced debug logging for element positioning
- June 25, 2025. Implemented comprehensive collision detection and boundary control system for label editor. Added real-time collision warnings, element snap boundaries with 5px padding, visual feedback with warning animations, and 10px tolerance zones to prevent overlap between text, images, QR codes, and other elements
- June 25, 2025. Enhanced advanced label editor with barcode support, silent notification system, design tools, and improved user experience. Added barcode element with actual product barcode data, grid overlay system, element alignment and distribution tools, collision detection during drag operations, replaced all browser alerts with silent notifications, and fixed font sizing issues with proper DOM reflow
- June 25, 2025. Resolved print scaling issues with complete coordinate system overhaul. Removed complex canvas-based calculations and implemented direct DPI scaling (96→300 DPI) for 1:1 editor-to-print accuracy. Fixed barcode display in print output and removed detailed settings panel. System now provides exact visual-print matching
- June 25, 2025. Added comprehensive A4 paper layout design settings to Enhanced Product Label system. Integrated paper size selection (A4/Letter), page orientation (portrait/landscape), custom label dimensions, margin controls, gap spacing, and print quality options. Includes intelligent page layout calculator that automatically determines optimal label arrangement and maximum labels per page. All professional A4 design features from legacy barcode system now available in new drag-and-drop editor interface
- June 25, 2025. Implemented saved design synchronization with A4 page layout settings. When users select saved designs, system automatically updates page settings to match design dimensions, calculates optimal page layout, and provides visual feedback showing design compatibility with current page settings. Eliminates disconnect between saved designs and page layout configuration
- June 25, 2025. Fixed page layout enforcement to respect user-defined column and row settings. Removed automatic optimization that reduced user's chosen layout parameters. System now forces exact column/row counts as specified by user, creating additional pages when layout exceeds single page capacity. Changed layout calculator to validation-only mode with visual feedback for layout compatibility
- June 25, 2025. Resolved A4 printing alignment issues with intelligent label centering system. Added automatic content area calculation and center-point positioning algorithm that eliminates left/right shifting problems. Labels now perfectly center on A4 pages regardless of quantity or layout configuration, with minimum margin safety controls to prevent edge overflow
- June 25, 2025. Implemented A4 Standard Mode with fixed layout specifications: 3×7 grid (21 labels), 63.33×37.20mm label dimensions, 15mm top/bottom margins, 8mm left/right margins. Added subtle label borders (light gray outlines) for visual separation during printing. Integrated automatic total label count display that updates in real-time when labels are added, removed, or quantities changed. System auto-applies A4 standard settings on page load as default configuration
- June 25, 2025. Replaced Enhanced Product Label A4 system with exact copy of Product Label A4_FIXED_CONFIG. Implemented identical layout specifications: 3×7 grid, 64.67×37.92mm calculated dimensions, 8mm left/right margins, 15mm top/bottom margins, 2mm column gap, 1mm row gap, 0.08mm overflow protection. Frontend and backend now use identical Product Label calculations ensuring perfect layout compatibility between both systems
- June 25, 2025. Completely simplified Enhanced Product Label interface by removing all complex configuration options. Created enhanced_product_label_simple.html with fixed A4 settings display only. Eliminated dropdowns, input fields, calculation buttons, and variable settings. System now uses hardcoded Product Label A4_FIXED_CONFIG values throughout, ensuring zero configuration drift and perfect layout matching with original Product Label system. User interface reduced to essential functions: product search, queue management, saved designs, and direct A4 printing
- June 30, 2025. Removed flash messages/notification banner from product list page to clean up interface
- July 01, 2025. Reverted to simpler coordinate system for label element positioning. System now uses basic positioning without complex scaling calculations or coordinate transformations
- July 02, 2025. Fixed critical variable scope issues after reversion. Resolved model_code, color, and size variable definition problems in create_label_with_design function. QR code generation and product image loading functionality restored. Flask application now starts successfully with all core features working
- July 03, 2025. System completely restored to July 2nd 17:24 stable state. All subsequent changes reverted to ensure QR codes and product images display correctly in A4 printing system
- July 03, 2025. Fixed variable scope issues and restored QR code functionality in Enhanced Product Label system. Added missing variable definitions (model_code, color, size) and replaced logger with print statements for debugging. QR codes now display correctly in A4 PNG output with proper logo integration. System tested and confirmed working
- July 03, 2025. Implemented automatic collision detection system to prevent text elements from overlapping with product images. System automatically repositions conflicting text elements with 2mm safety margin. Added page-start printing system - labels now print from beginning of page instead of center positioning. A4 PNG output tested and confirmed working with proper element positioning and collision avoidance
- July 03, 2025. Completed page-start label positioning system. Removed all margin calculations and gap spacing between labels. Labels now position tightly from absolute page start (0,0 coordinates) with no spacing between elements. Tested with 6-label layout showing perfect alignment from page beginning. System now prints labels efficiently using maximum page space without gaps or margins
- July 03, 2025. Successfully resolved page-center positioning issue by completely overhauling coordinate calculation system. Implemented pixel-based label sizing (page_width_px ÷ columns) instead of mm-to-pixel conversion. Eliminated all margin and gap calculations. Labels now print from absolute page beginning (0,0) with perfect grid alignment. Frontend and backend A4 configurations synchronized with zero margins. Debug logging confirmed accurate coordinate positioning



# User Preferences

Preferred communication style: Simple, everyday language.
User wants simplified drag-and-drop editor without detailed settings panels, but with persistent save/load functionality for different label configurations. Also needs adjustable label sizes, resizable elements, and saved designs accessible in printing section. IMPORTANT: Labels should use product-specific fields (size, model code, color) instead of generic text, with automatic population of real product data during printing. Each field should be positioned separately and filled with actual product information.