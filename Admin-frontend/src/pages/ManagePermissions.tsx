import { useState, useEffect, useCallback, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Check } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { useDepartments } from '@/contexts/DepartmentsContext';
import { DateRangePicker } from '@/components/permissions/DateRangePicker';
import { BulkActionsCard } from '@/components/permissions/BulkActionsCard';
import { PermissionSummaryCard } from '@/components/permissions/PermissionSummaryCard';
import axios from 'axios'; // Import axios

// Define the structure for your permissions matrix
type PermissionsMatrix = Record<number, Record<number, boolean>>;

// Define the DateRange type as expected by DateRangePicker and for sending to backend
interface DateRange {
  from: Date | undefined;
  to: Date | undefined;
}

// Define the interface for the payload sent to /api/permissions (POST)
interface SavePermissionsRequestPayload {
  allowed_pairs: { from_dept_id: number; to_dept_id: number; can_survey_self: boolean }[];
  start_date: string;
  end_date: string;
}

const API_BASE_URL = 'http://localhost:5000/api'; // Assuming your Flask backend runs on port 5000

const ManagePermissions = () => {
  const { departments, loading, error } = useDepartments(); 
  const { toast } = useToast();

  const departmentNames = useMemo(() => departments.map(d => d.name), [departments]);
  const departmentIds = useMemo(() => departments.map(d => d.id), [departments]);
  const departmentMap = useMemo(() => {
    return departments.reduce((acc, dept) => {
      acc[dept.id] = dept.name;
      return acc;
    }, {} as Record<number, string>);
  }, [departments]);

  // Initializing permissions: Default all to false, then load from backend
  const initializeEmptyPermissions = useCallback(() => {
    const matrix: PermissionsMatrix = {};
    departmentIds.forEach(fromId => {
      matrix[fromId] = {};
      departmentIds.forEach(toId => {
        matrix[fromId][toId] = false; // Default to not allowed
      });
    });
    return matrix;
  }, [departmentIds]);

  const [permissions, setPermissions] = useState<PermissionsMatrix>(initializeEmptyPermissions());
  const [dateRange, setDateRange] = useState<DateRange>({ from: undefined, to: undefined }); // State for date range
  const [isSaving, setIsSaving] = useState(false); // For Save Changes button
  const [isAlerting, setIsAlerting] = useState(false); // For Mail Alert Users button

  // Configure Axios to send cookies for this component's requests
  useEffect(() => {
    axios.defaults.withCredentials = true;
  }, []);

  // Effect to fetch initial permissions from backend once departments are loaded
  useEffect(() => {
    const fetchInitialPermissions = async () => {
        if (loading || error || departments.length === 0) {
            return; // Wait for departments to load or handle errors
        }

        try {
            const response = await axios.get(`${API_BASE_URL}/permissions`);
            const backendPermissions: { from_department_id: number; to_department_id: number; can_survey_self: boolean; start_date?: string; end_date?: string }[] = Array.isArray(response.data)
                ? response.data
                : [];

            const initialMatrix: PermissionsMatrix = initializeEmptyPermissions(); // Start with all false

            let initialStartDate: Date | undefined = undefined;
            let initialEndDate: Date | undefined = undefined;

            backendPermissions.forEach(perm => {
                if (departmentMap[perm.from_department_id] && departmentMap[perm.to_department_id]) {
                    // Only set permission if the 'from' and 'to' departments exist in our current list
                    // And only set if it's a cross-departmental permission OR if self-survey is explicitly true
                    if (perm.from_department_id !== perm.to_department_id || perm.can_survey_self) {
                        initialMatrix[perm.from_department_id][perm.to_department_id] = true;
                    }
                    
                    // Also, capture the date range from the first permission found, assuming consistency
                    if (!initialStartDate && perm.start_date) {
                        initialStartDate = new Date(perm.start_date);
                    }
                    if (!initialEndDate && perm.end_date) {
                        initialEndDate = new Date(perm.end_date);
                    }
                }
            });

            setPermissions(initialMatrix);
            // Set date range if loaded from backend
            if (initialStartDate && initialEndDate) {
                setDateRange({ from: initialStartDate, to: initialEndDate });
            }

        } catch (err: any) {
            console.error("Failed to fetch initial permissions:", err);
            toast({
                title: "Error",
                description: err.response?.data?.detail || "Failed to load permissions. Please check backend connection.",
                variant: "destructive",
            });
        }
    };

    fetchInitialPermissions();
  }, [departments, loading, error, departmentMap, initializeEmptyPermissions, toast]);


  // Recalculate permissions state when departments change (but let backend load override)
  // This useEffect ensures the matrix UI is set up correctly if departments change after initial load.
  useEffect(() => {
    if (!loading && !error && departments.length > 0) {
      // Re-initialize only if permissions haven't been loaded from backend yet,
      // or if the number of 'from' departments in state doesn't match current departments.
      if (Object.keys(permissions).length === 0 || 
          Object.keys(permissions).length !== departmentIds.length) {
          setPermissions(initializeEmptyPermissions());
      }
    }
  }, [departments, loading, error, initializeEmptyPermissions, permissions, departmentIds]);

  // Calculate stats for PermissionSummaryCard
  // totalPermissions should count all *toggleable* cells (excluding self-rating cells if they are never allowed)
  const actualToggleableCells = useMemo(() => {
    if (departments.length === 0) return 0;
    return departments.length * (departments.length - 1); // Excludes all self-rating cells
  }, [departments]);
  
  const currentAllowedCount = useMemo(() => {
      let count = 0;
      Object.entries(permissions).forEach(([fromIdStr, toDepts]) => {
          const fromId = Number(fromIdStr);
          Object.entries(toDepts).forEach(([toIdStr, isAllowed]) => {
              const toId = Number(toIdStr);
              // Count only permissions that are TRUE AND are NOT self-ratings
              if (isAllowed && fromId !== toId) {
                  count++;
              }
          });
      });
      return count;
  }, [permissions]);

  const currentRestrictedCount = actualToggleableCells - currentAllowedCount;
  const progressRate = actualToggleableCells > 0 ? Math.round((currentAllowedCount / actualToggleableCells) * 100) : 0;


  // Toggle permission for a specific cell
  const togglePermission = useCallback((fromId: number, toId: number) => {
      if (fromId === toId) return; // Self-rating is not allowed by UI toggle
      
      setPermissions(prev => {
          const newMatrix = { ...prev };
          if (!newMatrix[fromId]) {
              newMatrix[fromId] = {};
          }
          newMatrix[fromId][toId] = !newMatrix[fromId][toId]; // Toggle the boolean
          return newMatrix;
      });
  }, []);

  // Handle "Allow All" for a selected department
  const handleAllowAll = useCallback((selectedDeptName: string) => {
      const selectedDept = departments.find(d => d.name === selectedDeptName);
      if (!selectedDept) {
          toast({ title: "Error", description: "Selected department not found.", variant: "destructive" });
          return;
      }
      const selectedDeptId = selectedDept.id;

      setPermissions(prev => {
          const newPermissions = { ...prev };
          if (!newPermissions[selectedDeptId]) {
              newPermissions[selectedDeptId] = {};
          }

          departments.forEach(dept => {
              if (selectedDeptId !== dept.id) { // Do not toggle self-rating
                  newPermissions[selectedDeptId][dept.id] = true;
              }
          });
          return newPermissions;
      });

      toast({
          title: "Permissions Updated",
          description: `All permissions granted for ${selectedDeptName}`,
      });
  }, [departments, toast]);

  // Handle "Revoke All" for a selected department
  const handleRevokeAll = useCallback((selectedDeptName: string) => {
      const selectedDept = departments.find(d => d.name === selectedDeptName);
      if (!selectedDept) {
          toast({ title: "Error", description: "Selected department not found.", variant: "destructive" });
          return;
      }
      const selectedDeptId = selectedDept.id;

      setPermissions(prev => {
          const newPermissions = { ...prev };
          if (!newPermissions[selectedDeptId]) {
              newPermissions[selectedDeptId] = {};
          }

          departments.forEach(dept => {
              if (selectedDeptId !== dept.id) { // Do not toggle self-rating
                  newPermissions[selectedDeptId][dept.id] = false;
              }
          });
          return newPermissions;
      });

      toast({
          title: "Permissions Updated",
          description: `All permissions revoked for ${selectedDeptName}`,
      });
  }, [departments, toast]);

    // Handle saving changes to the backend
  const handleSaveChanges = useCallback(async () => {
    if (isSaving) { // Prevent multiple clicks
      toast({ title: "Please wait", description: "Save is already in progress.", variant: "default" });
      return;
    }
    if (loading || error || departments.length === 0) { // Ensure data is loaded
         toast({ title: "Error", description: "Cannot save: Departments data not fully loaded or error present.", variant: "destructive" });
         return;
    }
    if (!dateRange.from || !dateRange.to) {
        toast({ title: "Date Range Required", description: "Please select a valid date range before saving permissions.", variant: "destructive" });
        return;
    }

    setIsSaving(true);
    const allowedPairs: { from_dept_id: number; to_dept_id: number; can_survey_self: boolean }[] = [];
    
    // Iterate through all possible pairs to construct the payload based on the current matrix state
    departments.forEach(fromDept => {
        departments.forEach(toDept => {
            const fromId = fromDept.id;
            const toId = toDept.id;
            const isAllowed = permissions[fromId]?.[toId] || false; // Get current state from matrix

            // If the permission is currently allowed in the UI, and it's not a self-rating (which is disabled)
            if (isAllowed && fromId !== toId) {
                // For cross-departmental permissions from this UI, can_survey_self is always false
                allowedPairs.push({
                    from_dept_id: fromId,
                    to_dept_id: toId,
                    can_survey_self: false 
                });
            } else if (fromId === toId && isAllowed) { // This `isAllowed` would only be true if initial load permitted self-survey
                // If a self-survey is allowed from backend (e.g., initial load) and it's still true in the matrix
                // then we include it with can_survey_self as true.
                // This covers the case where the backend might allow self-survey, but the UI doesn't allow toggling it.
                // However, the current UI always shows "Self Rating not allowed", so `isAllowed` will be false here unless changed.
                // Let's refine based on backend model:
                // If the backend allows self-survey for a department, we need to send it.
                // The current UI *always* shows "Self Rating not allowed" and the button is disabled.
                // This means the `permissions` matrix will never have `true` for `fromId === toId` through user interaction.
                // So, the `allowedPairs` list should *not* contain self-rating entries where `isAllowed` is true,
                // unless you add an explicit UI toggle for self-survey.
                //
                // For now, based on the current UI where `fromId === toId` is always `false` in `permissions` after user interaction:
                // We only add cross-departmental permissions.
                allowedPairs.push({
                    from_dept_id: fromId,
                    to_dept_id: toId,
                    can_survey_self: true // If a self-survey was loaded from backend as 'true', we need to persist it as 'true'.
                                            // This requires knowing the `can_survey_self` status from initial load.
                                            // The initialMatrix setup already handles this.
                                            // So if `permissions[fromId][toId]` is true AND `fromId === toId`,
                                            // it implies it was loaded as an allowed self-survey.
                });
            }
        });
    });

    // Final logic for `allowedPairs` construction:
    const finalAllowedPairs: SavePermissionsRequestPayload['allowed_pairs'] = [];
    Object.entries(permissions).forEach(([fromIdStr, toDepts]) => {
        const fromId = Number(fromIdStr);
        Object.entries(toDepts).forEach(([toIdStr, isAllowed]) => {
            const toId = Number(toIdStr);

            // If the permission is marked as allowed in our local state:
            if (isAllowed) {
                // If it's a self-survey (fromId === toId), include it and mark can_survey_self as true.
                // The backend will then decide if it saves based on its own logic (e.g., if can_survey_self in DB is true).
                // Our UI (ManagePermissions.tsx) currently disables toggling self-survey cells,
                // so `isAllowed` would only be true here for self-surveys if it was loaded from the backend.
                finalAllowedPairs.push({
                    from_dept_id: fromId,
                    to_dept_id: toId,
                    can_survey_self: (fromId === toId) // Set true for self-survey, false for cross-departmental
                });
            }
        });
    });


    try {
        // Explicitly type the payload for Axios
        const payload: SavePermissionsRequestPayload = {
            allowed_pairs: finalAllowedPairs, // Use the new `finalAllowedPairs`
            start_date: dateRange.from!.toISOString(), // Use '!' for non-null assertion as we already checked
            end_date: dateRange.to!.toISOString(),     // Use '!' for non-null assertion as we already checked
        };

        await axios.post<any>(`${API_BASE_URL}/permissions`, payload); // Pass the payload object directly

        toast({
            title: "Permissions Saved",
            description: "Your permission changes have been saved successfully",
            variant: "default",
        });
    } catch (err: any) {
        console.error("Failed to save permissions:", err);
        toast({
            title: "Error",
            description: err.response?.data?.message || "Failed to save permissions. Please try again.",
            variant: "destructive",
        });
    } finally {
        setIsSaving(false);
    }
  }, [permissions, departmentIds, loading, error, toast, dateRange, departments, isSaving]);


  // Handle Mail Alert Users
  const handleMailAlert = useCallback(async () => {
    if (isAlerting) {
      toast({ title: "Please wait", description: "Mail alert is already in progress.", variant: "default" });
      return;
    }
    if (loading || error || departments.length === 0) {
        toast({ title: "Error", description: "Cannot send alert: Departments data not fully loaded or error present.", variant: "destructive" });
        return;
    }

    if (!dateRange.from || !dateRange.to) {
      toast({
        title: "Validation Error",
        description: "Please select a start and end date for the mail alert.",
        variant: "destructive",
      });
      return;
    }

    setIsAlerting(true);
    try {
      // Prepare the data to send to the backend. This should mirror what's *currently saved* or intended to be.
      // Filter out self-ratings if the UI doesn't allow toggling them.
      const currentAllowedPairs: { from_dept_id: number; to_dept_id: number; can_survey_self: boolean }[] = [];
      Object.entries(permissions).forEach(([fromIdStr, toDepts]) => {
          const fromId = Number(fromIdStr);
          Object.entries(toDepts).forEach(([toIdStr, isAllowed]) => {
              const toId = Number(toIdStr);
              // Only include allowed permissions that are NOT self-ratings for this UI
              if (isAllowed) { // If it's allowed in the matrix, add it.
                               // The `can_survey_self` flag will determine if it's a self-survey
                               // The UI doesn't allow toggling self-survey explicitly, so `isAllowed`
                               // for self-surveys would only be true if loaded from backend.
                currentAllowedPairs.push({
                    from_dept_id: fromId,
                    to_dept_id: toId,
                    can_survey_self: (fromId === toId) // Mark true for self-survey, false for cross-departmental
                });
              }
          });
      });

      const payload: SavePermissionsRequestPayload = { // Re-use the same payload type
          allowed_pairs: currentAllowedPairs,
          start_date: dateRange.from!.toISOString(),
          end_date: dateRange.to!.toISOString(),
      };

      await axios.post(`${API_BASE_URL}/permissions/mail-alert`, payload);

      toast({
        title: "Mail Alert Sent",
        description: "Permission alerts have been sent to all relevant users.",
        variant: "default",
      });
    } catch (err: any) {
      console.error("Failed to send mail alert:", err);
      toast({
        title: "Error",
        description: err.response?.data?.message || "Failed to send mail alert. Please try again.",
        variant: "destructive",
      });
    } finally {
      setIsAlerting(false);
    }
  }, [permissions, dateRange, departmentIds, loading, error, toast, isAlerting, departments]);
  
  // Display loading or error states
  if (loading) {
    return (
      <div className="flex justify-center items-center h-screen text-lg">
        <p>Loading departments and permissions...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex justify-center items-center h-screen text-lg text-red-500">
        <p>Error: {error}</p>
      </div>
    );
  }

  // Main component rendering
  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Manage Survey Permission</h1>
          <p className="text-muted-foreground">
            Control which departments can survey each other
          </p>
        </div>
        <Button onClick={handleSaveChanges} className="bg-blue-600 hover:bg-blue-700" disabled={isSaving}>
          {isSaving ? 'Saving...' : 'Save Changes'}
        </Button>
      </div>

      {/* Permission Matrix - Full Width */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <div className="inline-block min-w-full align-middle">
              <table className="min-w-full border-separate border-spacing-0">
                <thead>
                  <tr>
                    <th className="sticky left-0 z-10 bg-white border border-gray-200 px-3 py-3.5 text-sm font-semibold text-gray-900">
                      Department
                    </th>
                    {/* Use department.name for headers, department.id for key */}
                    {departments.map((dept) => (
                      <th
                        key={dept.id}
                        scope="col"
                        className="border border-gray-200 px-3 py-3.5 text-center text-sm font-semibold text-gray-900 min-w-[120px]"
                      >
                        {dept.name}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {/* Iterate over departments to create rows */}
                  {departments.map((fromDept) => (
                    <tr key={fromDept.id}>
                      <td className="sticky left-0 z-10 bg-gray-50 border border-gray-200 whitespace-nowrap px-3 py-4 text-sm font-medium text-gray-900">
                        {fromDept.name}
                      </td>
                      {/* Iterate over departments again for columns */}
                      {departments.map((toDept) => (
                        <td
                          key={`${fromDept.id}-${toDept.id}`}
                          className={`border border-gray-200 px-3 py-4 text-center ${
                            fromDept.id === toDept.id
                              ? 'bg-gray-200' // Self-rating background
                              : permissions[fromDept.id]?.[toDept.id]
                              ? 'bg-green-50' // Allowed background
                              : 'bg-white' // Not allowed background
                          }`}
                        >
                          {fromDept.id === toDept.id ? (
                            <div className="text-xs text-gray-500 text-center">
                              Self Rating<br />is not allowed
                            </div>
                          ) : (
                            <button
                              onClick={() => togglePermission(fromDept.id, toDept.id)}
                              className={`w-6 h-6 rounded-md flex items-center justify-center ${
                                permissions[fromDept.id]?.[toDept.id]
                                  ? 'bg-green-500 text-white'
                                  : 'bg-gray-200 text-gray-500'
                              }`}
                              aria-label={
                                permissions[fromDept.id]?.[toDept.id]
                                  ? `Revoke permission for ${fromDept.name} to survey ${toDept.name}`
                                  : `Grant permission for ${fromDept.name} to survey ${toDept.name}`
                              }
                            >
                              {permissions[fromDept.id]?.[toDept.id] ? <Check size={14} /> : null}
                            </button>
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Permission Summary and Bulk Actions - Below Matrix */}
      <div className="grid lg:grid-cols-2 gap-6">
        <PermissionSummaryCard
          totalPermissions={actualToggleableCells} 
          allowedPermissions={currentAllowedCount} 
          restrictedPermissions={currentRestrictedCount} 
          progressRate={progressRate} 
        />

        <BulkActionsCard
          departments={departmentNames} 
          onAllowAll={handleAllowAll}
          onRevokeAll={handleRevokeAll}
        />
      </div>

     {/* Date Range Picker - Below Summary/Bulk Actions */}
      <DateRangePicker onSelectDateRange={setDateRange} selectedDateRange={dateRange} /> {/* Correct prop name */}
      
      {/* Mail Alert Button - Bottom */}
      <div className="flex justify-end">
        <Button
          onClick={handleMailAlert}
          className="bg-blue-600 hover:bg-blue-700"
          disabled={isAlerting || !dateRange.from || !dateRange.to} // Disable if no date range or alerting
        >
          {isAlerting ? 'Sending Alerts...' : 'Mail Alert Users'}
        </Button>
      </div>
    </div>
  );
};

export default ManagePermissions;
