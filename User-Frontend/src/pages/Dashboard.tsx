
import MainLayout from '@/components/MainLayout/MainLayout';
import { useAuth } from '@/contexts/AuthContext';
import { useSurvey } from '@/contexts/SurveyContext';
import { Progress } from '@/components/ui/progress';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { useNavigate } from 'react-router-dom'; // Import useNavigate
import { Button } from '@/components/ui/button';

const Dashboard = () => {
  const { user } = useAuth();
  const { getSurveyProgress, surveySubmissions } = useSurvey();
  const navigate = useNavigate(); // Initialize useNavigate hook

  // This should now correctly call the function from SurveyContext
  const progress = getSurveyProgress();
  const progressPercentage = progress.total > 0 ? Math.round((progress.completed / progress.total) * 100) : 0;

  // Calculate department ratings for the chart (still dummy data for now)
  const departmentRatings = [
    { name: 'IT', rating: 85 },
    { name: 'HR', rating: 90 },
    { name: 'QA', rating: 85 },
    { name: 'SCM', rating: 70 },
    { name: 'TPM', rating: 88 },
    { name: 'CSD', rating: 95 },
  ];

  const handleBarClick = (data: any) => {
    if (data.rating < 80) {
      // Navigate to the remarks/response page for the specific department
      // You'll need to figure out how to map the department name to a survey ID or department ID
      // For now, let's just navigate to the general remarks-response page.
      // In a real app, you might pass `data.name` or an ID as a state or URL param.
      console.log(`Clicked on ${data.name} with low rating: ${data.rating}`);
      navigate('/remarks-response'); // Navigate to the remarks/response page
    }
  };

  return (
    <MainLayout title="Dashboard">
      <div className="px-6 py-4">
        <h2 className="text-2xl font-bold text-gray-800 mb-6">
          Welcome, {user?.name || user?.username}!
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {/* Survey Overview Card */}
          <Card className="col-span-1 lg:col-span-2 shadow-lg">
            <CardHeader>
              <CardTitle className="text-lg font-semibold text-gray-700">Department Performance Overview</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-[300px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={departmentRatings} margin={{ top: 20, right: 30, left: 0, bottom: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="name" />
                    <YAxis domain={[0, 100]} ticks={[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]} />
                    <Tooltip />
                    <Bar dataKey="rating" onClick={handleBarClick}>
                      {departmentRatings.map((entry, index) => (
                        <Cell 
                          key={`cell-${index}`} 
                          fill={entry.rating < 80 ? '#FF6B6B' : '#e5e7ff'} // Red for low rating, default for others
                          stroke={entry.rating >= 80 ? '#9b87f5' : '#FF6B6B'} 
                          strokeWidth={1}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="text-sm text-muted-foreground mt-2">
                *Click on Red Graph to view the remarks / improvement suggestions
              </div>
            </CardContent>
          </Card>

          {/* Survey Progress Card */}
          <Card className="shadow-lg">
            <CardHeader>
              <CardTitle className="text-lg font-semibold text-gray-700">Survey Progress</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <h3 className="font-medium mb-2">Completion: {progress.completed}/{progress.total}</h3>
                <Progress value={progressPercentage} className="h-2 bg-gray-200 [&>*]:bg-primary" />
                <p className="text-sm text-muted-foreground mt-1">
                  {progress.total - progress.completed} surveys remaining.
                </p>
              </div>
              
              <Button 
                className="w-full bg-primary hover:bg-primary/90 text-white"
                onClick={() => navigate('/departments')}
              >
                Start New Survey
              </Button>
              <Button 
                className="w-full bg-secondary hover:bg-secondary/90 text-gray-800"
                onClick={() => navigate('/excel')}
              >
                Download Reports
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </MainLayout>
  );
};

export default Dashboard;
