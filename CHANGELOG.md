# Changelog

Toutes les modifications notables de ce projet sont documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.5.0] - 2026-02-22


### 📚 Documentation


- Update changelog for v2.4.11


### 📝 Autres


- Improves user list grouping by parent account

Ensures sub-accounts appear directly after their parent to make the admin user list easier to scan and manage.

Cleans up template blocks to avoid prematurely closing the main block before extra scripts.
- Adds optional web search to AI wine insights

Adds configurable web search toggle and context size for prompts, ensuring parameter updates are persisted by reassigning the parameters map.

Extends the wine enrichment request to include the web search tool when enabled, and improves citation handling by extracting URL annotations as a fallback for missing source links.

Updates the default response schema to include an optional source URL field and improves insight header truncation in the UI for better readability.

## [2.4.11] - 2026-02-02


### 🐛 Corrigé


- Add build arguments for Docker image versioning
- Update Docker build arguments to use short SHA for versioning


### 📚 Documentation


- Update changelog for v2.4.10

## [2.4.10] - 2026-02-02


### 📚 Documentation


- Update changelog for v2.4.9


### 🚀 Ajouté


- Enhance changelog workflow to include release notes generation
- Enhance cellar metrics display and update functionality

## [2.4.9] - 2026-02-02


### ♻️ Modifié


- Update changelog generation to use local git-cliff installation


### 🚀 Ajouté


- Add application versioning and changelog generation workflow

## [2.4.7] - 2026-02-02


### 📝 Autres


- Refactor wine overview layout and styles for improved compactness and usability

- Adjusted padding and box-shadow for cellar metrics to enhance visual clarity.
- Reduced font sizes and margins for metric labels and values for a more compact design.
- Updated button styles to be smaller and more consistent across the interface.
- Simplified text in the overview section for brevity and clarity.
- Removed unnecessary card elements and adjusted layout for wine cards to improve space utilization.
- Implemented a modal for enriched wine information with dynamic content loading.
- Enhanced filter functionality with improved visibility and reset button states.

## [2.4.6] - 2026-02-02


### 🚀 Ajouté


- Add JavaScript and CSS minification steps to Docker workflow
- Enhance JavaScript and CSS minification with advanced options
- Optimize CSS minification command with updated options
- Revamp wine consumption UI with compact card layout and enhanced urgency legend

## [2.4.5] - 2026-02-02


### 🚀 Ajouté


- Implement password update functionality for admin users and enhance session management
- Implement mobile sidebar menu with overlay and navigation functionality
- Enhance badge color selection with live preview functionality in add and edit subcategory forms

## [2.4.4] - 2026-01-30


### 🚀 Ajouté


- Add click handler for wine cards to navigate to detail view

## [2.4.3] - 2026-01-30


### 🚀 Ajouté


- Add JSON response schema management and validation in prompt editing

## [2.4.2] - 2026-01-30


### 🚀 Ajouté


- Refactor wine import and enrichment process, enhance logging and error handling

## [2.4.1] - 2026-01-30


### 🚀 Ajouté


- Add wine-themed styles for photo import page and components
- Enhance wine consumption recommendations with urgency scoring and detailed reporting

## [2.4.0] - 2026-01-30


### 📝 Autres


- Refactors model imports for clarity

Updates imports to reference models via the `app.models` module.

This change improves code organization and avoids potential naming conflicts by explicitly specifying the location of model definitions.
- Add user logs, consumption, and OpenAI settings templates

- Created user_logs.html for displaying user-specific API call logs with statistics and pagination.
- Added consumption.html to show user's AI service consumption, including cost breakdown and date filtering.
- Introduced openai.html for managing OpenAI API key settings, including usage statistics and recent API calls.


### 🚀 Ajouté


- Add bottle detection service and image analysis functionality
- Enhance wine filtering functionality with interactive chips and reset buttons

## [2.3.0] - 2026-01-28


### 📝 Autres


- Implements scheduled tasks for weekly reports

Adds a scheduler for sending weekly reports and cleaning up old data.

This commit introduces a new scheduler process that runs independently
from the main application to handle tasks such as:

- Sending weekly email reports to users with summaries of their wine cellar activity.
- Cleaning up old email logs, activity logs, and API usage logs to maintain database performance.

The scheduler is configured via environment variables, allowing control over the
timing of the tasks.  An admin interface is also provided to manually trigger
these tasks.
- Adds wine pairing feature

Adds a new "wine pairing" feature, including a new blueprint
and navigation link to access wine suggestions.

## [2.2.0] - 2026-01-28


### 📝 Autres


- Implements email functionality and SMTP configuration

Adds email sending capabilities to the application.

Introduces SMTP configuration management for sending emails, including secure password storage using encryption.

Adds email address to user profiles and enables admin to manage user emails.

Includes database migrations to create the necessary tables and columns.

## [2.1.0] - 2026-01-28


### 📝 Autres


- Implements push notifications for cellar actions

Adds push notification functionality for admin and users.
This includes:

- An admin interface to send push notifications to all users, a single user, or a user's account family.
- Detailed push subscription list for administrators.
- Push notifications when a cellar or wine is created/deleted/consumed by a user's account family.
- Push notification when wine stock is low.

It leverages a new `PushSubscription` model and integrates with `push_notification_service`.
- Adds CSRF protection to notification form

Adds a hidden CSRF token field to the send notification form.

This helps protect against cross-site request forgery attacks
when submitting the form.
- Adds compact notification button to navbar

Implements a compact notification button in the navbar.

This commit introduces a new notification button in the navbar
that adapts its appearance based on the notification state
(enabled, disabled, or not subscribed). It uses icons and
title attributes for a cleaner and more informative user
experience in the compact navbar setting. The button also provides
visual feedback (spinner) while enabling push notifications.
- Improves push notification subscription process.

Enhances the push notification subscription process by adding more robust error handling and logging.

- Implements client-side error handling with fallback mechanisms to ensure a more resilient subscription flow.
- Adds server-side logging for debugging purposes, providing insights into subscription events and potential issues.
- Prevents endpoint re-registration errors by reassigning the push subscription to the current user if already existing.
- Implements a timeout for service worker readiness to prevent indefinite waiting.
- Improves PWA service worker and push notification handling

Enhances service worker registration by initiating it immediately instead of waiting for the window load event.

Adds extensive logging to the push notification initialization and subscription processes for better debugging and monitoring.

Includes error handling and retries for VAPID key retrieval to improve the robustness of push subscriptions.
- Adds service worker for PWA functionality

Adds a service worker to enable Progressive Web App (PWA) functionality.

The service worker is served from the root scope to allow broader control.  It also configures appropriate headers to ensure correct caching behavior and scope.  The client-side JavaScript is updated to register the service worker with the correct scope.
- Cleans VAPID key before using it.

Ensures the VAPID key is properly cleaned by removing surrounding quotes and spaces before being used.
Also, adds a console log to display a truncated version of the cleaned VAPID key.
This prevents errors caused by incorrectly formatted keys.
- Improves push subscription handling

Adds logging and error handling to the push subscription process.

This change enhances the robustness of the push subscription endpoint by:
- Adding more detailed logging to track subscription requests and key presence.
- Implementing comprehensive error handling with rollback to prevent data inconsistencies in case of exceptions.
- Providing more informative error messages to the client in case of subscription failure.
- Exempts and cleans VAPID key for push notifications

Exempts new API endpoints related to push notifications from CSRF protection.

Also, cleans the VAPID public key by removing surrounding quotes, ensuring correct usage. Adds logging for the VAPID key being sent.
- Improves push notification handling and reliability

Enhances push notification functionality by:

- Exempting the API blueprint from CSRF protection to allow JavaScript-based requests.
- Adding more robust error handling and logging for push subscription requests.
- Normalizing push subscription data to handle inconsistencies across browsers.
- Adding debug logging to service worker and main script.
- Fixing CDN fallback for bootstrap and quagga to static resources.

These changes aim to improve the reliability and user experience of push notifications, particularly in error scenarios and across different browser environments.
- Improves service worker caching strategy

Enhances the service worker's caching mechanism by adding exceptions for cross-origin requests and local vendor files to facilitate debugging.

Also, modifies the cache-first strategy to attempt fetching from the network as a fallback when the cache lookup fails or when an error occurs during initial fetch, providing greater resilience.
- Refrains from intercepting cross-origin requests

Avoids intercepting cross-origin requests in the service worker.
This ensures that requests to external origins are handled directly
by the browser, preventing potential interference with CORS policies
and improving compatibility with external resources.
- Improves proxy support and cookie security

Adds support for reverse proxies like Traefik to ensure correct scheme/host handling.

Configures cookie settings to be more robust by allowing the `SameSite` attribute to be set via an environment variable.  Defaults to 'Lax' if the variable is not set or contains an invalid value.

Updates the service worker to remove outdated assets and correct offline page routes. This ensures a smoother offline experience by caching only relevant resources and directing users to the correct URLs.
- Adds CSRF debugging logs to login route

Adds logging to the login route to assist in debugging CSRF issues.

The logs include information about the request's security status,
protocol, user agent, referrer, session cookie presence, and CSRF
token presence.
- Improves CSRF protection and logging

Adds CSRF error handling with detailed logging to aid in debugging.

Introduces a configuration option to exempt the login route from CSRF protection, controlled by the `WTF_CSRF_EXEMPT_LOGIN` environment variable. This allows disabling CSRF for login, potentially simplifying integration with certain authentication flows.

Exempts login route from CSRF if configured.
- Allows session protection level configuration

Makes the session protection level configurable via an environment variable.

This allows operators to adjust the security level of the application's sessions without modifying the code directly, improving flexibility and deployment configuration options.
- Removes CSRF exemption for login

Removes the configuration option and related logic to exempt the login route from CSRF protection.

The previous CSRF handling was overly verbose and logged potentially sensitive information. This change simplifies the CSRF handling by removing the login exemption and related logging, relying on standard CSRF protection for the login route.
- Improves overall design and UI/UX

Enhances the user interface and experience by implementing a modern design system with improved typography, cards, buttons, inputs and other components.

This includes a redesigned login page, improved wine cards, admin user management page, and a more visually appealing presentation of cellar and wine information. New CSS variables have been introduced to control spacing and sizing to provide consistent design and improve responsiveness.

## [2.0.1] - 2026-01-27


### 📝 Autres


- Fixes Swagger UI mixed-content errors

Ensures Swagger UI uses the same scheme as the request.

This prevents mixed-content errors when the API is accessed
through HTTPS behind a proxy like nginx by checking for the
X-Forwarded-Proto header.

## [2.0.0] - 2026-01-27


### 📝 Autres


- Optimize Docker build layer caching
- Fix apt cache mount for Docker builds
- Improves wine management and UI

Adds features for better wine management and enhances the user interface.

- Implements the ability to set and clear a default cellar for users, streamlining the wine addition process and providing a more personalized experience.
- Introduces a "Restock" action in consumption history, allowing users to easily correct mistakes and return consumed wines to their cellar.
- Enhances the search functionality with name filtering and stock status options.
- Improves navigation and adds visual enhancements.
- Includes database migrations to add the `default_cellar_id` column to the `user` table.
- Ignores the 'data' directory to prevent sensitive data from being included in the repository.
- Implements responsive search bar

Adds a responsive search bar that adapts to different screen sizes.

The search bar is displayed as a standard input on larger screens and as a full-width overlay on smaller screens. This improves the user experience on mobile devices by providing a larger, more accessible search area. It also adds a mobile search toggle and associated Javascript to handle display logic.
- Adds API blueprint with token authentication

Implements a REST API blueprint for programmatic data access, secured with token-based authentication.

- Introduces API token management with creation, revocation, and usage tracking.
- Exempts API routes from CSRF protection, relying on API tokens for authentication.
- Implements rate limiting to prevent abuse and ensure fair usage.
- Provides various endpoints for managing wines, cellars, categories, and consumption history.
- Implements sub-account functionality

Adds the ability to create sub-accounts linked to a main account.

This change introduces a parent_id column to the user table, allowing users to be associated with a parent account. Sub-accounts inherit resources (cellars, wines) from their parent account.

- Modifies the admin interface to allow creating sub-accounts
- Updates API and UI to use the parent account's ID when accessing resources for sub-accounts
- Prevents sub-accounts from being administrators or having sub-accounts themselves
- Implements API, webhooks, admin features

Extends the application with a REST API, enabling token-based authentication and CRUD operations for managing wines and cellars.

Adds webhook functionality, allowing users to subscribe to events and receive notifications.

Enhances the admin interface with activity logs, user quota management, and global statistics.

Improves UI with dark mode support and interactive tutorials.
- Adds push notifications and API documentation

Adds push notification functionality with subscription management and test endpoint.

Improves API documentation with Swagger UI integration and token authentication.

Adds offline mode support using service worker.

## [1.0.5] - 2025-11-14


### 📝 Autres


- Handle decimal custom field values
- Updates CSP to include unpkg.com

Updates the Content Security Policy to include unpkg.com for both styles and scripts.

This allows loading resources from unpkg.com, providing access to additional libraries and assets.
- Add comments to wine consumptions
- Ensure wine consumption comment column exists

## [1.0.4] - 2025-10-20


### 📝 Autres


- Allow script
- Adds CSRF protection to forms

Adds a hidden CSRF token input to several forms to protect against cross-site request forgery attacks. This enhances the security of the application by validating the origin of form submissions.

## [1.0.3] - 2025-10-20


### 📝 Autres


- Update workflows
- Replace migration runner with database initializer
- Allow pushes to feat branches in Docker workflow
- Updates Docker image build workflow

Modifies the Docker image build workflow to correctly handle feature branches.

This change ensures that Docker images are built and pushed for all feature branches, not just the main branch. It updates the workflow to use a more generic condition to trigger the build and push steps and adjusts the metadata action accordingly.

## [1.0.2] - 2025-10-20


### 📝 Autres


- Fix default category migration with badge colors

## [1.0.1] - 2025-10-20


### 📝 Autres


- Error in migrations. Try to insert an existing column
- Fix : Migrations orders

## [1.0.0] - 2025-10-20


### 🐛 Corrigé


- Error


### 📝 Autres


- ✨ First commit with basic functionnality
- Add cellar management and link wines to cellars
- Allow configuring bottle capacity per cellar floor
- Add startup schema migration runner
- Add bottle lifecycle actions and history tracking
- Add automated wine enrichment and detail views
- Integrate OpenAI enrichment fallback
- Improves wine insight generation

Refines the wine insight generation process by updating the OpenAI client to use the latest API features and preferred models.

- Updates the Wine model to use descending order for `weight` and `created_at`
- Prioritizes newer, more efficient language models for insight generation.
- Adapts the OpenAI client to use the new `text` format instead of `response_format` for JSON schema requests, aligning with API updates.
- Enforces the inclusion of all required fields in the generated insights.
- Switch to official OpenAI Python client
- Simplify OpenAI integration
- Improves wine information retrieval with OpenAI

Enhances the wine information service by integrating OpenAI for enriching wine data.

This commit refactors the wine information service to leverage the OpenAI API for providing contextual insights about wines. It introduces comprehensive logging for debugging and monitoring the OpenAI integration, including request/response logging. The changes also streamline the process of constructing prompts and parsing responses from OpenAI, making the process more robust and informative. The commit removes the Wikipedia and DuckDuckGo providers.
- Adds alcohol categories and subcategories

Introduces a system for categorizing alcohol types (e.g., wine, spirits, beer) and their subcategories (e.g., red wine, amber rum, IPA).

This change includes:
- Database model definitions for AlcoholCategory and AlcoholSubcategory
- Migration scripts to create and populate the tables with default values
- UI elements for managing categories and subcategories
- Updates to the wine creation and edition forms to allow selecting a subcategory for a wine.

This enhances organization and filtering of wines within the application.
- Adds multi-criteria wine search

Implements a new search feature allowing users to find wines based on subcategory and food pairing.

This enhances the user experience by enabling more targeted wine discovery.
It also improves wine selection.
- Adds wine consumption urgency feature

Implements a new feature to display wines that should be consumed soon based on their age and potential aging information.

This feature analyzes wine insights for mentions of aging potential and calculates an urgency score.
The wines are then sorted by urgency score and displayed on a new page with visual cues.

Also, adds a link to this page in the base template.
- Refactors wine insight storage to ensure data consistency

Improves the wine enrichment process by ensuring data consistency when storing insights.

Previously, new insights were added without removing existing ones, potentially leading to stale or duplicated information. Now, the system removes all existing insights before adding new ones, ensuring that the data reflects the most recent enrichment process. Also adds a check to avoid processing insights if the iterable of insights is empty.

Updates the wine info service prompt to ask for 4-6 insights instead of 3-5.
- Adds contextual category badges

Improves UI clarity by adding category-specific badges.

Introduces a function to map subcategories to CSS classes,
allowing for visually distinct badges based on category.

Updates templates to utilize this function via a Jinja2 filter,
enhancing the presentation of subcategory information.
- Improves wine display by cellar and subcategory

Organizes the wine list on the main page by cellar and then by subcategory for better user experience.

This change modifies the wine query to include subcategory information and orders the results by cellar and subcategory, then restructures the data for display in the template.

The template is also updated to iterate through the organized data, displaying wines grouped by cellar and subcategory.
- Implements cellar editing functionality

Enables users to edit existing cellars, including their name, type, and floor capacities.

Adds a new route and template for editing cellar information.
Includes validation to ensure that the provided data is valid.
Allows users to dynamically add or remove floors from a cellar.
- Ensures columns are added only if missing

Adds a check to ensure that `badge_bg_color` and
`badge_text_color` columns are added to the
`alcohol_subcategory` table only if they don't
already exist, preventing potential errors.
- Refactors cellar type to use categories

Replaces the cellar type string field with a category, allowing for more flexible and organized cellar management.

This includes:
- Adding a `CellarCategory` model with name, description, and display order.
- Creating a migration to populate default cellar categories and migrate existing `cellar_type` values to the new category.
- Modifying the cellar add and edit forms to use a category selection instead of a type selection.
- Updating the cellar listing to display the cellar category.
- Adds CSRF protection and secures redirects

Implements CSRF protection to prevent cross-site request forgery attacks by integrating Flask-WTF.

Secures redirects by validating the target URL, ensuring it is a relative path within the application to prevent open redirect vulnerabilities.
- ✨ Removes app.py and refactors app structure

This commit removes the monolithic `app.py` file and prepares for a more modular application structure using blueprints.

It will allow for better organization and maintainability by separating concerns into distinct modules.
- Refonte du tableau de bord d'accueil
- Refonte de la page d'accueil

Refond la page d'accueil en tableau de bord synthétique
- Add configurable bottle fields and volume requirement
- Add UI to manage alcohol field requirements
- Support dynamic bottle fields configurable per category
- Implements flexible field management with JSON storage

This commit introduces a new approach to managing bottle fields by storing all data in the `extra_attributes` JSON field.

This change enables editing, renaming, and deleting custom fields, and ensures consistency by treating all fields uniformly. A migration script is included to transfer existing data to the new storage format.

The commit also includes UI changes for editing and deleting fields, and updates the wine blueprint to use the new JSON storage.
- Improves wine attribute handling and field requirements

- Uses extra_attributes for wine details instead of direct attributes. This makes wine data more flexible and consistent.
- Implements field requirement inheritance for categories and subcategories, with global defaults.
- Adds debug output for field settings.

These changes enhance data consistency and provides more control over which fields are enabled/required for different wine categories.
- Add comprehensive statistics dashboard
- Fix SQLite migration for wine timestamps
- Improve statistics dashboard layout and assets
- Fix SRI hashes for statistics dashboard assets
- Adds more country coordinates
- Fix login redirect and session persistence
- Fix url parsing import in auth blueprint
- Add modern cellar overview for all alcohols
- Generate and store stylized wine labels
- Add CSRF tokens to wine action forms
- Improves wine label image handling

Adds functionality to upload, remove, and optimize wine label images.

This change introduces the ability to upload a custom label image for each wine.
The image is resized to a maximum width of 800 pixels and converted to JPEG format with optimized compression.
A checkbox is added to allow users to remove the existing image.

Also updates the OpenAI image model.
- Add Dockerfile
- 🗑️ Remove old files and prepare security audit
- Mitigate major security findings
- Add multi-user support with admin controls
- Relax CSP for CDN assets
- Allow administrators to delete users
- Fix missing entrypoint
- Missing wsgy.py


### 🚀 Ajouté


- Manage subcategory badge colors in database

<!-- generated by git-cliff -->
