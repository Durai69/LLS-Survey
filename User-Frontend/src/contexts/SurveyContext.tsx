// src/contexts/SurveyContext.tsx
import React, { createContext, useContext, useState, ReactNode, useEffect } from 'react';
import axios from 'axios';
import { useToast } from '@/components/ui/use-toast';
import { Department } from '@/contexts/DepartmentContext'; 

const API_BASE_URL = 'http://127.0.0.1:5000/api';

interface SurveyQuestion {
    id: number;
    text: string;
    type: 'rating' | 'text' | 'multiple_choice'; 
    order: number;
    options?: { id: number; text: string; value?: string }[]; 
}

interface SurveyData {
    id: number;
    title: string;
    description: string;
    created_at: string;
    questions: SurveyQuestion[];
    dept_name: string;
    internal_supplier: string;
    date: string;
    overall_customer_rating?: number;
    rating_description?: string;
    suggestions?: string;
}

interface QuestionAnswerSubmission {
    id: number; 
    rating?: number; 
    remarks?: string; 
    selected_option_id?: number; 
}

interface SurveySubmissionPayload {
    user_id: number; 
    answers: QuestionAnswerSubmission[];
    suggestion?: string; 
    survey_id: number; 
}

interface SurveySubmission {
  id: number;
  survey_id: number;
  user_id: number;
  submitted_at: string;
  final_suggestion?: string;
}


interface SurveyContextType {
    currentSurvey: SurveyData | null;
    loadingSurvey: boolean;
    error: string | null;
    fetchSurveyById: (surveyId: string | number) => Promise<SurveyData | null>;
    submitSurveyResponse: (surveyId: string | number, payload: SurveySubmissionPayload) => Promise<boolean>;
    departments: Department[];
    surveySubmissions: SurveySubmission[];
    getSurveyProgress: () => { completed: number; total: number }; 
    fetchSurveySubmissions: () => Promise<void>; 
}

const SurveyContext = createContext<SurveyContextType | undefined>(undefined);

export const SurveyProvider = ({ children }: { children: ReactNode }) => {
    const [currentSurvey, setCurrentSurvey] = useState<SurveyData | null>(null);
    const [loadingSurvey, setLoadingSurvey] = useState<boolean>(false);
    const [error, setError] = useState<string | null>(null);
    const [departments, setDepartments] = useState<Department[]>([]);
    const [surveySubmissions, setSurveySubmissions] = useState<SurveySubmission[]>([]);

    const { toast } = useToast();

    const fetchDepartments = async () => {
        try {
            const response = await axios.get<Department[]>(`${API_BASE_URL}/departments`);
            setDepartments(response.data);
        } catch (err) {
            console.error("Failed to fetch departments in SurveyContext:", err);
            toast({
                title: "Error",
                description: "Failed to load departments.",
                variant: "destructive",
            });
        }
    };

    const fetchSurveySubmissions = async () => {
        try {
            // Placeholder: Fetch actual survey submissions from your backend
            // Example: const response = await axios.get(`${API_BASE_URL}/users/${userId}/submissions`);
            // setSurveySubmissions(response.data);
            console.log("Fetching survey submissions (dummy data for now)...");
            const dummySubmissions: SurveySubmission[] = [
                // Add some dummy submissions if needed for testing progress bar
                // { id: 1, survey_id: 1, user_id: 1, submitted_at: new Date().toISOString() },
            ];
            setSurveySubmissions(dummySubmissions);
        } catch (error) {
            console.error("Failed to fetch survey submissions:", error);
            toast({
                title: "Error",
                description: "Failed to load survey submissions.",
                variant: "destructive",
            });
        }
    };

    const fetchSurveyById = async (surveyId: string | number): Promise<SurveyData | null> => {
        setLoadingSurvey(true);
        setError(null);
        try {
            const response = await axios.get<SurveyData>(`${API_BASE_URL}/surveys/${surveyId}`);
            setCurrentSurvey(response.data);
            return response.data;
        } catch (err: any) {
            console.error('Failed to fetch survey details:', err);
            setError(err.response?.data?.detail || 'Could not load survey. Please try again.');
            toast({
                title: 'Error',
                description: 'Could not load survey. Please try again.',
                variant: 'destructive',
            });
            return null;
        } finally {
            setLoadingSurvey(false);
        }
    };

    const submitSurveyResponse = async (surveyId: string | number, payload: SurveySubmissionPayload): Promise<boolean> => {
        try {
            const response = await axios.post(`${API_BASE_URL}/surveys/${surveyId}/submit_response`, payload);
            toast({
                title: 'Survey Submitted',
                description: 'Your survey has been submitted successfully.',
                variant: "default", 
            });
            fetchSurveySubmissions();
            return true;
        } catch (err: any) {
            console.error('Failed to submit survey:', err);
            setError(err.response?.data?.detail || 'Failed to submit survey. Please try again.');
            toast({
                title: 'Submission Failed',
                description: err.response?.data?.detail || 'There was an error submitting your survey.',
                variant: 'destructive',
            });
            return false;
        }
    };

    const getSurveyProgress = () => {
        const total = departments.length; 
        const completed = surveySubmissions.length; 

        return { completed, total };
    };

    useEffect(() => {
        fetchDepartments();
        fetchSurveySubmissions(); 
    }, []);

    return (
        <SurveyContext.Provider value={{ 
            currentSurvey, 
            loadingSurvey, 
            error, 
            fetchSurveyById, 
            submitSurveyResponse, 
            departments, 
            surveySubmissions, 
            getSurveyProgress,
            fetchSurveySubmissions
        }}>
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
