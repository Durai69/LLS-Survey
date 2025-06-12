
import React from 'react';
import { useNavigate } from 'react-router-dom';
import MainLayout from '@/components/MainLayout/MainLayout';
import { useAuth } from '@/contexts/AuthContext';
import { useSurvey } from '@/contexts/SurveyContext';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useToast } from '@/components/ui/use-toast';
import { cn } from '@/lib/utils';

const DepartmentSelection = () => {
  const { user } = useAuth();
  const { departments, surveySubmissions } = useSurvey();
  const navigate = useNavigate();
  const { toast } = useToast();

  // Filter out user's own department
  const availableDepartments = departments.filter(
    (dept) => dept.name !== user?.department
  );

  // Create a map of completed surveys by department ID
  const completedSurveys = new Map(
    surveySubmissions.map((submission) => [submission.departmentId, true])
  );

  const handleDepartmentSelect = (departmentId: string, departmentName: string) => {
    if (completedSurveys.has(departmentId)) {
      toast({
        title: 'Already Completed',
        description: `You have already submitted a survey for ${departmentName}.`,
      });
      return;
    }

    navigate(`/survey/${departmentId}`);
  };

  return (
    <MainLayout>
      <div className="px-6">
        <h2 className="text-2xl font-semibold mb-6 text-center">
          Select a Department to Submit Survey
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
          {availableDepartments.map((department) => {
            const isCompleted = completedSurveys.has(department.id);
            
            return (
              <Card
                key={department.id}
                className={cn(
                  "cursor-pointer hover:shadow-md transition-shadow",
                  isCompleted && "opacity-80"
                )}
                onClick={() => handleDepartmentSelect(String(department.id), department.name)}
              >
                <CardContent className="p-4 flex items-center justify-between">
                  <div className="flex items-center">
                    <div className={cn(
                      "w-4 h-4 rounded-full mr-3",
                      isCompleted ? "bg-green-500" : "border border-gray-300"
                    )}>
                      {isCompleted && (
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          viewBox="0 0 24 24"
                          fill="white"
                          className="w-4 h-4"
                        >
                          <path
                            fillRule="evenodd"
                            d="M19.916 4.626a.75.75 0 01.208 1.04l-9 13.5a.75.75 0 01-1.154.114l-6-6a.75.75 0 011.06-1.06l5.353 5.353 8.493-12.739a.75.75 0 011.04-.208z"
                            clipRule="evenodd"
                          />
                        </svg>
                      )}
                    </div>
                    <span className="font-medium">{department.name}</span>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>

        <div className="mt-12">
          <h3 className="text-lg font-medium mb-4">Survey Rules Reminder :</h3>
          <ol className="list-decimal list-inside space-y-2 text-gray-700">
            <li>You cannot rate your own department.</li>
            <li>You can rate each department only once. No edits are allowed after submission.</li>
            <li>All survey questions are mandatory. You must answer all 5 questions.</li>
            <li>Remarks are mandatory if you rate below 2 stars.</li>
            <li>You can add suggestions or feedback.</li>
            <li>Submit before the deadline. Surveys may close after a specific date.</li>
            <li>Be honest and constructive. Ratings are confidential but help improve department performance.</li>
            <li>Once submitted, surveys are locked. Contact the admin if there's a mistake.</li>
          </ol>
        </div>
      </div>
    </MainLayout>
  );
};

export default DepartmentSelection;
