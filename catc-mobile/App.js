import React, { useState, useEffect } from 'react';
import { 
  StyleSheet, Text, View, TextInput, TouchableOpacity, 
  FlatList, SafeAreaView, Alert, ActivityIndicator, 
  StatusBar, RefreshControl
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import axios from 'axios';
import { MotiView, AnimatePresence } from 'moti'; // Smooth animations
import { LinearGradient } from 'expo-linear-gradient'; // Vibrant backgrounds

const BASE_URL = 'https://catcreg.online/api';

export default function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [step, setStep] = useState(1); 
  const [studentId, setStudentId] = useState('');
  const [otpCode, setOtpCode] = useState('');
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    checkLoginStatus();
  }, []);

  const checkLoginStatus = async () => {
    const token = await AsyncStorage.getItem('userToken');
    if (token) {
      setIsLoggedIn(true);
      fetchDashboard(token);
    }
  };

  const handleSendOTP = async () => {
    if (!studentId) {
      Alert.alert("Input Required", "Please enter your Student ID.");
      return;
    }
    setLoading(true);
    try {
      const res = await axios.post(`${BASE_URL}/login/`, { student_id: studentId.trim().toUpperCase() });
      setStep(2);
      Alert.alert("Code Sent", `Code sent to ${res.data.masked_email}`);
    } catch (err) {
      if (err.response && err.response.status === 429) {
        Alert.alert("Wait a moment", "Please wait 60 seconds before trying again.");
      } else {
        Alert.alert("Error", "Student ID not found.");
      }
    }
    setLoading(false);
  };

  const handleVerifyOTP = async () => {
    if (!otpCode) return;
    setLoading(true);
    try {
      const res = await axios.post(`${BASE_URL}/verify/`, { 
        student_id: studentId.toUpperCase(), 
        otp_code: otpCode 
      });
      await AsyncStorage.setItem('userToken', res.data.access);
      setIsLoggedIn(true);
      fetchDashboard(res.data.access);
    } catch (err) {
      Alert.alert("Error", "Invalid or expired OTP.");
    }
    setLoading(false);
  };

  const fetchDashboard = async (token) => {
    try {
      const res = await axios.get(`${BASE_URL}/dashboard/`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setRequests(res.data);
    } catch (err) {
      handleLogout();
    }
    setRefreshing(false);
  };

  const onRefresh = async () => {
    setRefreshing(true);
    const token = await AsyncStorage.getItem('userToken');
    fetchDashboard(token);
  };

  const handleLogout = async () => {
    await AsyncStorage.clear();
    setIsLoggedIn(false);
    setStep(1);
    setStudentId('');
    setOtpCode('');
  };

  const getStatusColor = (status) => {
    if (status === 'READY') return '#28a745';
    if (status === 'PAYMENT_REQUIRED') return '#fd7e14';
    if (status === 'REJECTED') return '#dc3545';
    if (status === 'PENDING') return '#6c757d';
    return '#0d6efd';
  };

  // UI: LOGIN SCREEN
  if (!isLoggedIn) {
    return (
      <LinearGradient colors={['#0d6efd', '#004fb8']} style={styles.loginWrapper}>
        <StatusBar barStyle="light-content" />
        
        <MotiView 
          from={{ opacity: 0, scale: 0.5 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ type: 'spring', duration: 1000 }}
          style={{ alignItems: 'center', marginBottom: 40 }}
        >
          <Text style={styles.logoTitle}>CATC PORTAL</Text>
          <Text style={styles.logoSub}>Student Document System</Text>
        </MotiView>
        
        <MotiView 
          from={{ opacity: 0, translateY: 50 }}
          animate={{ opacity: 1, translateY: 0 }}
          style={styles.loginCard}
        >
          <AnimatePresence exitBeforeEnter>
            {step === 1 ? (
              <MotiView 
                key="step1"
                from={{ opacity: 0, translateX: -20 }}
                animate={{ opacity: 1, translateX: 0 }}
                exit={{ opacity: 0, translateX: -20 }}
              >
                <Text style={styles.cardLabel}>STUDENT ID</Text>
                <TextInput 
                  style={styles.input} 
                  placeholder="S000000" 
                  placeholderTextColor="#aaa"
                  value={studentId} 
                  onChangeText={setStudentId}
                  autoCapitalize="characters"
                />
                <TouchableOpacity activeOpacity={0.8} onPress={handleSendOTP}>
                  <LinearGradient colors={['#0d6efd', '#007bff']} style={styles.primaryBtn}>
                    {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.btnText}>GET OTP</Text>}
                  </LinearGradient>
                </TouchableOpacity>
              </MotiView>
            ) : (
              <MotiView 
                key="step2"
                from={{ opacity: 0, translateX: 20 }}
                animate={{ opacity: 1, translateX: 0 }}
                exit={{ opacity: 0, translateX: 20 }}
              >
                <Text style={styles.cardLabel}>6-DIGIT CODE</Text>
                <TextInput 
                  style={styles.input} 
                  placeholder="000000" 
                  placeholderTextColor="#aaa"
                  keyboardType="numeric"
                  maxLength={6}
                  value={otpCode} 
                  onChangeText={setOtpCode}
                />
                <TouchableOpacity activeOpacity={0.8} onPress={handleVerifyOTP}>
                  <LinearGradient colors={['#28a745', '#218838']} style={styles.primaryBtn}>
                    {loading ? <ActivityIndicator color="#fff" /> : <Text style={styles.btnText}>VERIFY & LOGIN</Text>}
                  </LinearGradient>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => setStep(1)} style={{marginTop: 20}}>
                  <Text style={styles.linkText}>← Use different ID</Text>
                </TouchableOpacity>
              </MotiView>
            )}
          </AnimatePresence>
        </MotiView>
      </LinearGradient>
    );
  }

  // UI: DASHBOARD SCREEN
  return (
    <SafeAreaView style={styles.safeContainer}>
      <StatusBar barStyle="dark-content" />
      <View style={styles.header}>
        <MotiView from={{ translateX: -20, opacity: 0 }} animate={{ translateX: 0, opacity: 1 }}>
          <Text style={styles.headerTitle}>My Requests</Text>
          <Text style={styles.headerUser}>ID: {studentId}</Text>
        </MotiView>
        <TouchableOpacity style={styles.logoutBtn} onPress={handleLogout}>
          <Text style={styles.logoutText}>Logout</Text>
        </TouchableOpacity>
      </View>

      <FlatList
        data={requests}
        keyExtractor={item => item.id.toString()}
        contentContainerStyle={{padding: 15}}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
        renderItem={({ item, index }) => (
          <MotiView
            from={{ opacity: 0, translateY: 20 }}
            animate={{ opacity: 1, translateY: 0 }}
            transition={{ type: 'timing', duration: 500, delay: index * 100 }} // Staggered Entry
            style={styles.card}
          >
            <View style={styles.cardRow}>
              <Text style={styles.docName}>{item.doc_name}</Text>
              <MotiView 
                animate={{ opacity: item.status === 'READY' || item.status === 'PAYMENT_REQUIRED' ? [1, 0.5, 1] : 1 }}
                transition={{ loop: true, duration: 1500 }}
              >
                <Text style={[styles.status, {color: getStatusColor(item.status)}]}>
                  {item.status.replace('_', ' ')}
                </Text>
              </MotiView>
            </View>
            <Text style={styles.detail}>Method: {item.delivery_method}</Text>
            {item.tracking_number && (
              <MotiView from={{ scale: 0.9 }} animate={{ scale: 1 }} style={styles.lbcBox}>
                <Text style={styles.lbcText}>LBC Tracking: {item.tracking_number}</Text>
              </MotiView>
            )}
          </MotiView>
        )}
        ListEmptyComponent={
          <MotiView from={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1000 }} style={{marginTop: 100, alignItems: 'center'}}>
            <Text style={{color: '#999'}}>No requests found. Swipe down to refresh.</Text>
          </MotiView>
        }
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  loginWrapper: { flex: 1, justifyContent: 'center', padding: 25 },
  logoTitle: { fontSize: 42, fontWeight: '900', color: '#fff', textAlign: 'center', letterSpacing: -1 },
  logoSub: { fontSize: 16, color: 'rgba(255,255,255,0.7)', textAlign: 'center', fontWeight: '600' },
  loginCard: { backgroundColor: '#fff', borderRadius: 25, padding: 30, elevation: 20, shadowColor: '#000', shadowOffset: { width: 0, height: 10 }, shadowOpacity: 0.2, shadowRadius: 15 },
  cardLabel: { fontSize: 12, fontWeight: '800', color: '#888', marginBottom: 8, letterSpacing: 1 },
  input: { borderBottomWidth: 2, borderBottomColor: '#eee', fontSize: 22, marginBottom: 30, paddingVertical: 10, color: '#333', fontWeight: 'bold' },
  primaryBtn: { padding: 18, borderRadius: 15, alignItems: 'center', shadowColor: '#0d6efd', shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.3, shadowRadius: 8, elevation: 5 },
  btnText: { color: '#fff', fontWeight: 'bold', fontSize: 16, letterSpacing: 1 },
  linkText: { color: '#0d6efd', textAlign: 'center', fontSize: 14, fontWeight: '700' },
  
  safeContainer: { flex: 1, backgroundColor: '#f8f9fa' },
  header: { backgroundColor: '#fff', padding: 20, paddingTop: 40, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', borderBottomWidth: 1, borderBottomColor: '#eee' },
  headerTitle: { fontSize: 26, fontWeight: '800', color: '#1a1a1a' },
  headerUser: { fontSize: 13, color: '#888', fontWeight: '600' },
  logoutBtn: { backgroundColor: '#fff', paddingVertical: 8, paddingHorizontal: 15, borderRadius: 10, borderWidth: 1, borderBottomColor: '#f8d7da', borderColor: '#f5c6cb' },
  logoutText: { color: '#dc3545', fontWeight: 'bold', fontSize: 13 },
  card: { backgroundColor: '#fff', borderRadius: 20, padding: 20, marginBottom: 15, shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.05, shadowRadius: 10, elevation: 3 },
  cardRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 10 },
  docName: { fontSize: 17, fontWeight: '700', color: '#333', flex: 1 },
  status: { fontSize: 12, fontWeight: '800', textTransform: 'uppercase' },
  detail: { fontSize: 14, color: '#666', fontWeight: '500' },
  lbcBox: { marginTop: 15, backgroundColor: '#f0f7ff', padding: 12, borderRadius: 12, borderLeftWidth: 5, borderLeftColor: '#0d6efd' },
  lbcText: { color: '#0d6efd', fontWeight: 'bold', fontSize: 13 }
});