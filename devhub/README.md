import React, { useState, useEffect } from 'react';

export default function App() {
  const [telemetryActive, setTelemetryActive] = useState(true);

  useEffect(() => {
    console.log("Hackatime telemetry engine active.");
  }, []);

  return (
    <div className="min-h-screen bg-slate-900 text-white p-8">
      <h1 className="text-3xl font-bold">Hackatime Studio Dashboard</h1>
      <p className="text-slate-400 mt-2">Authentic developer telemetry session active.</p>
    </div>
  );
}