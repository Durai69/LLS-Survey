// Assuming your SurveyContext.tsx looks something like this.
// You need to ensure all Axios instances or fetch calls in it send cookies.

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import axios from 'axios';
import { useAuth } from '@/contexts/AuthContext'; // Assuming you use useAuth to check auth status
import { useToast } from '@/components/ui/use-toast';

const API_BASE_URL = 'http://127.0.0.1:5000';

// Define your interfaces
export interface QuestionData {
  id: number;
  text: string;
  type: 'rating' | 'text' | 'multiple_choice';
  order: number;
  category: string;
  options?: { id: number; text: string; value: string | null }[];
}

export interface SurveyData {
  id: number;
  title: string;
  description: string;
  created_at: string;
  rated_dept_name: string; // The name of the department being rated
  managing_dept_name: string; // The name of the department managing this survey
  rated_department_id: number;
  managing_department_id: number;
  questions: QuestionData[];
}

interface SurveyContextType {
  surveys: SurveyData[];
  fetchSurveys: () => Promise<void>;
  fetchSurveyById: (id: number) => Promise<SurveyData | null>;
  submitSurveyResponse: (surveyId: number, answers: any[], overallData: { overall_customer_rating?: number; rating_description?: string; suggestion?: string }) => Promise<boolean>;
  // Add other survey-related functions here (e.g., fetch remarks)
  isLoadingSurveys: boolean;
  error: string | null;
}

const SurveyContext = createContext<SurveyContextType | undefined>(undefined);

export const SurveyProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [surveys, setSurveys] = useState<SurveyData[]>([]);
  const [isLoadingSurveys, setIsLoadingSurveys] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { isAuthenticated, isLoading: isAuthLoading } = useAuth(); // Get isAuthenticated and isLoading from AuthContext
  const { toast } = useToast();

  // Configure Axios to send cookies with every request from this context
  axios.defaults.withCredentials = true;

  const fetchSurveys = async () => {
    if (!isAuthenticated) {
      console.log("Not authenticated, skipping fetchSurveys.");
      setIsLoadingSurveys(false); // Stop loading if not authenticated
      setError("Authentication required to fetch surveys.");
      return;
    }

    setIsLoadingSurveys(true);
    setError(null);
    try {
      const response = await axios.get<SurveyData[]>(`${API_BASE_URL}/api/surveys`);
      setSurveys(response.data);
    } catch (err: any) {
      console.error('Failed to fetch departments (surveys) in SurveyContext:', err);
      setError(err.response?.data?.detail || 'Failed to load surveys.');
      toast({
        title: "Error fetching surveys",
        description: err.response?.data?.detail || 'Failed to load surveys.',
        variant: "destructive",
      });
    } finally {
      setIsLoadingSurveys(false);
    }
  };

  const fetchSurveyById = async (id: number): Promise<SurveyData | null> => {
    if (!isAuthenticated) {
      console.log("Not authenticated, skipping fetchSurveyById.");
      setError("Authentication required to fetch survey details.");
      return null;
    }

    setIsLoadingSurveys(true); // Re-use this loading state for simplicity or create a specific one
    setError(null);
    try {
      const response = await axios.get<SurveyData>(`${API_BASE_URL}/api/surveys/${id}`);
      return response.data;
    } catch (err: any) {
      console.error('Failed to fetch survey details:', err);
      setError(err.response?.data?.detail || 'Failed to load survey details.');
      toast({
        title: "Error fetching survey",
        description: err.response?.data?.detail || 'Failed to load survey details.',
        variant: "destructive",
      });
      return null;
    } finally {
      setIsLoadingSurveys(false);
    }
  };

  const submitSurveyResponse = async (surveyId: number, answers: any[], overallData: { overall_customer_rating?: number; rating_description?: string; suggestion?: string }): Promise<boolean> => {
    if (!isAuthenticated) {
      toast({
        title: "Authentication Required",
        description: "Please log in to submit a survey.",
        variant: "destructive",
      });
      return false;
    }
    
    try {
      const payload = {
        answers: answers,
        overall_customer_rating: overallData.overall_customer_rating,
        rating_description: overallData.rating_description,
        suggestion: overallData.suggestion
      };
      const response = await axios.post(`${API_BASE_URL}/api/surveys/${surveyId}/submit_response`, payload);
      toast({
        title: "Survey Submitted",
        description: (response.data as { message?: string })?.message || "Your survey has been submitted successfully!",
      });
      return true;
    } catch (err: any) {
      console.error('Failed to submit survey response:', err);
      toast({
        title: "Submission Failed",
        description: err.response?.data?.detail || "There was an error submitting your survey.",
        variant: "destructive",
      });
      return false;
    }
  };


  // Effect to fetch surveys only when authenticated and auth state is ready
  useEffect(() => {
    // Only fetch if authentication check is complete and user is authenticated
    if (!isAuthLoading && isAuthenticated) {
      fetchSurveys();
    } else if (!isAuthLoading && !isAuthenticated) {
      // If auth check is complete and not authenticated, set loading to false
      setIsLoadingSurveys(false);
      setError("Not authenticated.");
    }
  }, [isAuthenticated, isAuthLoading]); // Dependencies: run when these change


  return (
    <SurveyContext.Provider value={{ surveys, fetchSurveys, fetchSurveyById, submitSurveyResponse, isLoadingSurveys, error }}>
      {children}
    </SurveyContext.Provider>
  );
};

export const useSurvey = (): SurveyContextType => {
  const context = useContext(SurveyContext);
  if (context === undefined) {
    throw new Error('useSurvey must be used within a SurveyProvider');
  }
  return context;
};
