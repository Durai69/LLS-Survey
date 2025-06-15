Project Information Overview
Project Title: LLS Survey and Administration Platform

Purpose:
This system is designed to facilitate survey management and data collection by providing distinct interfaces and functionalities for two primary user types: regular users and administrators. It ensures secure access to relevant features and data based on their assigned roles.

Key System Components & Their Functions:

User Application (User-frontend)

Access Point: Typically accessed via http://localhost:8080 (or a similar address).
Functionality: This is the primary interface for general users. It allows registered users to log in, access their personalized dashboard, participate in surveys, view their individual survey results, and manage their personal profile.
Admin Application (Admin-frontend)

Access Point: Typically accessed via http://localhost:3000 (or a similar address).
Functionality: This is a separate, dedicated interface for system administrators. It provides robust tools for managing the entire survey system, including:
Creating, editing, and deploying new surveys.
Managing user accounts and roles.
Viewing comprehensive survey data and analytics.
Overseeing system configurations.
Shared Components Directory

Location: A dedicated directory (e.g., Shared/) that holds common UI components, utility functions, or logic that is utilized by both the User Application and the Admin Application.
Key Example: The Login.tsx component, which handles the user authentication form and initial role-based redirection, is a prime example of a component housed here for reusability across both frontends. This reduces code duplication and centralizes login logic.
Backend API (Flask Application)

Access Point: Located at http://127.0.0.1:5000 (or a similar address).
Functionality: This is the central brain of the application. It handles all data processing, user authentication, authorization (determining user roles), and serves as the communication bridge between the frontend applications and the database. Both the User and Admin applications interact with this API to perform operations.
User Roles & Workflow:

The system supports two distinct roles, each with its own workflow after successful login:

1. Regular User Workflow:

Login: Users navigate to the User Application login page (which uses the shared Login.tsx component).
Authentication: They provide their unique username and password. The system's backend verifies these credentials and confirms their role as 'user'.
Redirection: Upon successful login, regular users are automatically redirected to their dedicated User Dashboard within the User Application (e.g., http://localhost:8081/dashboard).
Access: From their dashboard, they can access features relevant to regular users, such as taking surveys or viewing their personal survey history.
2. Administrator Workflow:

Login: Administrators navigate to the Admin Application login page (which also uses the shared Login.tsx component).
Authentication: They provide their specific administrative username and password. The system's backend verifies these credentials and confirms their role as 'admin'.
Redirection: Upon successful login, administrators are automatically redirected to the Admin Dashboard within the Admin Application (e.g., http://localhost:8080/dashboard).
Access: From their dashboard, they have full access to management tools and system-wide data.
This setup ensures that all users are directed to the appropriate interface and granted the correct level of access based on their identity and role, maintaining security and a streamlined user experience. The use of a shared login component streamlines development and ensures consistent authentication logic.
