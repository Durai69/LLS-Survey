import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { useToast } from '@/components/ui/use-toast'; // Correct path to useToast

const API_BASE_URL = 'http://127.0.0.1:5000';
const AUTH_LOCAL_STORAGE_KEY = 'insightPulseUser';

export interface User {
  id: number; // Ensure this is present and correctly typed
  username: string;
  name: string; // Ensure 'name' is explicitly a string
  email: string;
  department: string;
  role: string;
  is_active: boolean; // Ensure this is present and correctly typed
}

interface AuthContextType {
  user: User | null;
  login: (username: string, password: string) => Promise<User | null>;
  logout: () => void;
  isAuthenticated: boolean;
  isLoading: boolean; // Add isLoading to context type
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true); // Initialize isLoading
  const navigate = useNavigate();
  const { toast } = useToast();

  // Function to refresh authentication status (from local storage and backend)
  const refreshAuth = async () => {
    setIsLoading(true);
    try {
      console.log("Attempting to verify authentication status...");
      
      // First, try to load from local storage
      const storedUser = localStorage.getItem(AUTH_LOCAL_STORAGE_KEY);
      if (storedUser) {
        try {
          const parsedUser: User = JSON.parse(storedUser);
          // Basic validation for essential user properties before setting state
          if (parsedUser && parsedUser.id !== undefined && parsedUser.username && parsedUser.role && typeof parsedUser.is_active === 'boolean') {
            setUser(parsedUser);
            setIsAuthenticated(true);
            console.log("User data restored from local storage:", parsedUser.username);
          } else {
            console.warn("Invalid user data found in local storage. Clearing...");
            localStorage.removeItem(AUTH_LOCAL_STORAGE_KEY);
          }
        } catch (e) {
          console.error("Failed to parse user from local storage, clearing:", e);
          localStorage.removeItem(AUTH_LOCAL_STORAGE_KEY);
        }
      }

      // Then, verify with backend for token validity (even if loaded from local storage)
      const response = await fetch(`${API_BASE_URL}/verify_auth`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include', // Important for sending JWT cookie
      });

      if (response.ok) {
        const data = await response.json();
        console.log("Verify Auth Response Data (from backend):", data); 
        // Backend's /verify_auth also returns a nested 'user' object
        if (data.isAuthenticated && data.user && data.user.id !== undefined && data.user.username && data.user.role && typeof data.user.is_active === 'boolean') {
          setUser(data.user);
          setIsAuthenticated(true);
          localStorage.setItem(AUTH_LOCAL_STORAGE_KEY, JSON.stringify(data.user)); // Update local storage with fresh data
        } else {
          console.warn("Verify Auth: Invalid user data from backend or not authenticated. Clearing session.", data);
          setUser(null);
          setIsAuthenticated(false);
          localStorage.removeItem(AUTH_LOCAL_STORAGE_KEY);
        }
      } else {
        // This is expected if no valid token is present (e.g., initial load, token expired)
        console.log(`Verify Auth failed with status ${response.status}. Session cleared.`);
        setUser(null);
        setIsAuthenticated(false);
        localStorage.removeItem(AUTH_LOCAL_STORAGE_KEY);
      }
    } catch (error) {
      console.error('Error during verify_auth fetch:', error);
      toast({
        title: "Authentication Check Failed",
        description: "Could not connect to the authentication server.",
        variant: "destructive",
      });
      setUser(null);
      setIsAuthenticated(false);
      localStorage.removeItem(AUTH_LOCAL_STORAGE_KEY);
    } finally {
      setIsLoading(false);
    }
  };

  // Run refreshAuth on component mount
  useEffect(() => {
    refreshAuth();
  }, []);

  const login = async (username: string, password: string): Promise<User | null> => {
    try {
      console.log("Attempting login for username:", username);
      const response = await fetch(`${API_BASE_URL}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
        credentials: 'include', // Important for sending/receiving JWT cookie
      });

      if (!response.ok) {
        const errorData = await response.json();
        toast({
          title: "Login failed",
          description: errorData.detail || "Invalid username or password",
          variant: "destructive",
        });
        console.error("Login API returned non-OK status:", response.status, errorData);
        return null;
      }

      const responseJson = await response.json(); 
      console.log("Login successful full response data from backend:", responseJson); 

      // CRITICAL FIX: Extract the nested 'user' object
      const userData: User = responseJson.user; 

      // Validate essential properties of the extracted user data
      if (userData && userData.id !== undefined && userData.username && userData.role && typeof userData.is_active === 'boolean') {
        setUser(userData);
        setIsAuthenticated(true);
        // Store the *extracted user data* in local storage
        localStorage.setItem(AUTH_LOCAL_STORAGE_KEY, JSON.stringify(userData)); 

        toast({
          title: "Login successful",
          description: `Welcome back, ${userData.name || userData.username}`, // Use name, fallback to username
          variant: "default", 
        });

        return userData;
      } else {
        toast({
          title: "Login failed",
          description: "Invalid user data received from server. Missing ID, username, role, or active status.",
          variant: "destructive",
        });
        console.error("Login: Invalid user data structure after successful fetch and parsing:", userData);
        return null;
      }

    } catch (error) {
      console.error('Login fetch error:', error);
      toast({
        title: "Login failed",
        description: "Unable to connect to the server or unexpected network error.",
        variant: "destructive",
      });
      return null;
    }
  };

  const logout = async () => {
    try {
        console.log("Attempting logout...");
        const response = await fetch(`${API_BASE_URL}/logout`, {
            method: 'POST',
            credentials: 'include', 
        });
        if (!response.ok) {
            console.error("Logout failed on server:", await response.json());
            toast({ title: "Logout Failed", description: "Could not log out on the server.", variant: "destructive" });
        } else {
            console.log("Logout successful on server.");
        }
    } catch (error) {
        console.error("Error during logout request:", error);
    } finally {
        setUser(null);
        setIsAuthenticated(false);
        localStorage.removeItem(AUTH_LOCAL_STORAGE_KEY);
        toast({
            title: "Logged out",
            description: "You have been successfully logged out",
            variant: "default", 
        });
        navigate('/login');
    }
  };

  return (
    <AuthContext.Provider value={{ user, login, logout, isAuthenticated, isLoading }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
